"""Netflix-style discovery rows over stored mining outputs.

This module never trains a model, never writes Parquet, and never connects to
Snowflake. Ranking scores are ranking signals, not purchase probabilities.
Association rules describe co-purchase, not causation. Catalog and order-history
frames may come from PostgreSQL when FOODPULSE_DISCOVERY_OPERATIONAL_SOURCE is
postgres; stored ranks, association, and ratings stay on Parquet.
"""

from __future__ import annotations

from app.services import analytics_service as analytics
from app.services import discovery_operational
from app.services.analytics_service import AnalyticsDataError

DEFAULT_LIMIT = 8
THIN_HISTORY_ORDERS = 2
MIN_SUPPORT_COUNT = 14
MIN_CONFIDENCE = 0.3
MIN_LIFT = 1.0

FOOD_REASON_COPY = {
    "associated with a previously purchased item": "Often bought with something you already ordered",
    "frequently purchased cuisine": "Based on cuisines you already order",
    "highly rated in preferred cuisine": "High restaurant-level sample rating in a cuisine you already order",
    "previously reordered item": "Based on your previous orders",
    "general pick for limited history": "Popular choice while your order history is still thin",
}
RESTAURANT_REASON_COPY = {
    "previously highly rated restaurant": "Based on a restaurant you already used",
    "highly rated in preferred cuisine": "High restaurant-level sample rating in a cuisine you already order",
    "frequently purchased cuisine": "Based on cuisines you already order",
    "highly rated restaurant": "Strong restaurant-level sample rating",
    "general pick for limited history": "Popular choice while your order history is still thin",
}

NOTICE = (
    "These rows read stored recommendation, association, order, rating, and "
    "sentiment files. Scores are ranking signals, not purchase probabilities. "
    "Association is not causation. Star values are restaurant-level averages from "
    "sample reviews, not live public ratings and not dish ratings. "
    "There is no save, like, or dislike action."
)
RATING_LABEL = "Restaurant sample avg"
RATING_SOURCE = (
    "restaurant_features.avg_rating is the mean of sample reviews for that restaurant. "
    "Reviews have no food_item_id. This is not a live public rating and not a dish rating."
)
SECTION_SOURCES = {
    "picked_for_you": "food_recommendations.parquet",
    "popular_choices": "orders.parquet",
    "similar_to_what_you_like": "orders.parquet",
    "frequently_bought_together": "association_rules.parquet",
    "restaurants_for_you": "restaurant_recommendations.parquet",
    "explore_something_new": "orders.parquet",
}
SECTION_EXPLANATIONS = {
    "picked_for_you": {
        "algorithm": (
            "Offline baseline ranker: cuisine fit, association, restaurant sample rating, "
            "familiarity, and popularity. The stored score sorts the list; it is not a purchase probability."
        ),
        "data_source": "food_recommendations.parquet",
        "kind": "personalized",
        "fallback": False,
        "reason": "Stored dish rank for this sample customer.",
    },
    "popular_choices": {
        "algorithm": "Count of completed-order lines (status lowercased to completed) across every sample customer.",
        "data_source": "orders.parquet and order_items.parquet",
        "kind": "global",
        "fallback": False,
        "reason": "Sample-wide popularity, not a personal list.",
    },
    "similar_to_what_you_like": {
        "algorithm": "Take this customer's most-ordered restaurant cuisine, then rank other dishes in that cuisine by completed-order volume.",
        "data_source": "orders.parquet, order_items.parquet, restaurants.cuisine_type",
        "kind": "cuisine_history",
        "fallback": False,
        "reason": "Other dishes in the cuisine this customer ordered most. Not ingredient similarity.",
    },
    "frequently_bought_together": {
        "algorithm": (
            "Stored Apriori rules kept when this customer bought the antecedent, has not bought the consequent, "
            "and support_count, confidence, and lift meet the project thresholds. Co-purchase is not causation."
        ),
        "data_source": "association_rules.parquet",
        "kind": "association",
        "fallback": False,
        "reason": "A later dish that appeared with something this customer already ordered.",
    },
    "restaurants_for_you": {
        "algorithm": "Offline baseline restaurant ranker using cuisine fit, restaurant sample rating, familiarity, and popularity.",
        "data_source": "restaurant_recommendations.parquet",
        "kind": "personalized",
        "fallback": False,
        "reason": "Stored restaurant rank for this sample customer.",
    },
    "explore_something_new": {
        "algorithm": "Completed-order volume among cuisines absent from this customer's history, excluding dishes already shown above.",
        "data_source": "orders.parquet and the food catalog",
        "kind": "new_cuisine",
        "fallback": False,
        "reason": "Popular dishes from cuisines this customer has not ordered.",
    },
}
CATALOG_FALLBACK_EXPLANATION = {
    "algorithm": (
        "Completed-order volume among catalog dishes or restaurants that match the selected cuisine or category. "
        "This is not a stored personal rank, not collaborative filtering, and not an association rule."
    ),
    "data_source": "orders.parquet, order_items.parquet, and the food catalog",
    "kind": "cuisine_catalog",
    "fallback": True,
    "reason": "Stored suggestions did not match the filter, so matching catalog items are shown by sample popularity.",
}
COLD_START_EXPLANATION = {
    "algorithm": "Completed-order volume across the sample because this customer has no matching stored rank.",
    "data_source": "orders.parquet and order_items.parquet",
    "kind": "global",
    "fallback": True,
    "reason": "No stored personal rank was available, so popular sample items are shown instead.",
}
MISSING_EMPTY = {
    "picked_for_you": "Stored food recommendations are unavailable, so this personalized row cannot be built.",
    "popular_choices": "Completed-order files are unavailable, so global popularity cannot be ranked.",
    "similar_to_what_you_like": "Order history is unavailable, so cuisine similarity cannot be built.",
    "frequently_bought_together": "Stored association rules are unavailable, so this row cannot be built.",
    "restaurants_for_you": "Stored restaurant recommendations are unavailable, so this personalized row cannot be built.",
    "explore_something_new": "Completed-order files are unavailable, so new-cuisine dishes cannot be ranked.",
}


def discovery(
    customer_id: str,
    limit: int = DEFAULT_LIMIT,
    min_support_count: int = MIN_SUPPORT_COUNT,
    min_confidence: float = MIN_CONFIDENCE,
    min_lift: float = MIN_LIFT,
    cuisine: str | None = None,
    category: str | None = None,
) -> dict[str, object]:
    """Build discovery sections for one customer from stored files."""
    if not customer_id.strip() or "/" in customer_id or "\\" in customer_id:
        raise AnalyticsDataError("customer_id is invalid", status_code=422)
    if limit < 1:
        raise AnalyticsDataError("limit must be at least 1", status_code=422)
    identifier = customer_id.strip()
    cuisine_filter = _filter_value(cuisine)
    category_filter = _filter_value(category)
    unavailable: list[str] = []
    discovery_operational.reset_frames()
    try:
        payload = _discovery_payload(
            identifier,
            limit,
            min_support_count,
            min_confidence,
            min_lift,
            cuisine_filter,
            category_filter,
            unavailable,
        )
    finally:
        discovery_operational.reset_frames()
    return payload


def _discovery_payload(
    identifier: str,
    limit: int,
    min_support_count: int,
    min_confidence: float,
    min_lift: float,
    cuisine_filter: str | None,
    category_filter: str | None,
    unavailable: list[str],
) -> dict[str, object]:
    catalog = _catalog(unavailable)
    history = _history(identifier, catalog, unavailable)
    picked_native = _picked_for_you(identifier, catalog, history, limit, unavailable, cuisine_filter, category_filter)
    picked, picked_fallback = _maybe_food_catalog_fallback(
        picked_native,
        catalog,
        limit,
        cuisine_filter,
        category_filter,
        role="picked",
        allow_unfiltered=True,
    )
    popular_foods, popular_restaurants = _popular(catalog, limit, unavailable, cuisine_filter, category_filter)
    similar_native = _similar(catalog, history, picked_native, limit, cuisine_filter, category_filter)
    similar, similar_fallback = _maybe_food_catalog_fallback(
        similar_native,
        catalog,
        limit,
        cuisine_filter,
        category_filter,
        role="similar",
        allow_unfiltered=False,
        exclude={item["id"] for item in picked if item.get("kind") == "food"} | set(history.get("purchased_foods") or set()),
    )
    together = _bought_together(
        identifier, catalog, history, limit, min_support_count, min_confidence, min_lift, unavailable, cuisine_filter, category_filter
    )
    restaurants_native = _restaurants_for_you(identifier, catalog, history, limit, unavailable, cuisine_filter, category_filter)
    restaurants, restaurant_fallback = _maybe_restaurant_catalog_fallback(
        restaurants_native,
        catalog,
        limit,
        cuisine_filter,
        category_filter,
        allow_unfiltered=True,
    )
    used_foods = {
        item["id"]
        for item in picked + popular_foods + similar + together
        if item.get("kind") == "food"
    }
    explore_native = _explore(catalog, history, used_foods, limit, cuisine_filter, category_filter)
    explore, explore_fallback = _maybe_food_catalog_fallback(
        explore_native,
        catalog,
        limit,
        cuisine_filter,
        category_filter,
        role="explore",
        allow_unfiltered=False,
        exclude=used_foods | set(history.get("purchased_foods") or set()),
    )
    sections = [
        _section(
            "picked_for_you",
            "Picked for You",
            "Personalized stored food ranks for this customer. Ranking scores are not purchase probabilities.",
            "stored recommendation rank",
            picked,
            "No stored food recommendations for this customer.",
            "personalized",
        ),
        _section(
            "popular_choices",
            "Popular Choices",
            "Global completed-order volume across all customers. This row does not use the selected customer.",
            "completed_orders",
            popular_foods + popular_restaurants,
            "Completed-order volume is unavailable.",
            "global",
        ),
        _section(
            "similar_to_what_you_like",
            "Similar to What You Like",
            "Other dishes in the cuisine this customer ordered most. Not ingredient similarity.",
            "cuisine match plus completed-order volume",
            similar,
            "This customer has no completed-order cuisine to match.",
            "cuisine_history",
        ),
        _section(
            "frequently_bought_together",
            "Frequently Bought Together",
            "Association rules from this customer's completed orders, ranked by lift. Association is not causation.",
            "lift, confidence, and support_count",
            together,
            "No stored association rule meets the evidence threshold for this customer's orders.",
            "association",
        ),
        _section(
            "restaurants_for_you",
            "Restaurants for You",
            "Personalized stored restaurant ranks. Stars are restaurant sample averages, not live public ratings.",
            "stored recommendation rank",
            restaurants,
            "No stored restaurant recommendations for this customer.",
            "personalized",
        ),
        _section(
            "explore_something_new",
            "Explore Something New",
            "Popular dishes from cuisines this customer has not ordered, excluding items already shown above.",
            "completed_orders among unseen cuisines",
            explore,
            "No supported alternative remains after removing already shown dishes.",
            "new_cuisine",
        ),
    ]
    _apply_catalog_fallback_metadata(
        sections,
        {
            "picked_for_you": picked_fallback,
            "similar_to_what_you_like": similar_fallback,
            "restaurants_for_you": restaurant_fallback,
            "explore_something_new": explore_fallback,
        },
        cuisine_filter,
        category_filter,
    )
    _apply_empty_kinds(sections, unavailable, history)
    if cuisine_filter or category_filter:
        unused: list[str] = []
        picked_all = _picked_for_you(identifier, catalog, history, limit, unused)
        popular_foods_all, popular_restaurants_all = _popular(catalog, limit, unused)
        similar_all = _similar(catalog, history, picked_all, limit)
        together_all = _bought_together(
            identifier, catalog, history, limit, min_support_count, min_confidence, min_lift, unused
        )
        restaurants_all = _restaurants_for_you(identifier, catalog, history, limit, unused)
        explore_all = _explore(catalog, history, used_foods, limit)
        by_id = {str(section["id"]): section for section in sections}
        _annotate_filter_context(by_id["picked_for_you"], picked_all, cuisine_filter, category_filter)
        _annotate_filter_context(
            by_id["popular_choices"],
            popular_foods_all + popular_restaurants_all,
            cuisine_filter,
            category_filter,
        )
        _annotate_filter_context(by_id["similar_to_what_you_like"], similar_all, cuisine_filter, category_filter)
        _annotate_filter_context(by_id["frequently_bought_together"], together_all, cuisine_filter, category_filter)
        _annotate_filter_context(by_id["restaurants_for_you"], restaurants_all, cuisine_filter, category_filter)
        _annotate_filter_context(by_id["explore_something_new"], explore_all, cuisine_filter, category_filter)
    return {
        "source": "processed_parquet",
        "customer_id": identifier,
        "notice": NOTICE,
        "rating_notice": RATING_SOURCE,
        "history": history["summary"],
        "unavailable": unavailable,
        "filters": {
            "cuisines": catalog["cuisines"],
            "categories": catalog["categories"],
            "cuisine_categories": catalog["cuisine_categories"],
            "applied": {"cuisine": cuisine_filter, "category": category_filter},
        },
        "sections": sections,
        "persistence": {
            "save": False,
            "like": False,
            "dislike": False,
            "note": "No save, like, or dislike endpoint exists. The page does not invent those actions.",
        },
        "skipped": {
            "images": "food_items.parquet and restaurants.parquet have no image URL column.",
            "ingredients": "No ingredient or recipe file exists.",
        },
    }


def plain_reason(stored: object, kind: str) -> tuple[str, bool]:
    """Map a stored ranker reason to a customer-facing sentence."""
    text = "" if stored is None else str(stored)
    table = FOOD_REASON_COPY if kind == "food" else RESTAURANT_REASON_COPY
    fallback = text == "general pick for limited history"
    return table.get(text, text or "Stored ranking reason"), fallback


def _section(
    section_id: str,
    title: str,
    description: str,
    metric: str,
    items: list[dict[str, object]],
    empty_message: str,
    scope: str,
) -> dict[str, object]:
    explanation = dict(SECTION_EXPLANATIONS.get(section_id, {}))
    return {
        "id": section_id,
        "title": title,
        "description": description,
        "metric": metric,
        "scope": scope,
        "items": items,
        "empty_message": empty_message,
        "empty_kind": None if items else "no_results",
        "explanation": explanation,
        "fallback_kind": None,
    }


def _catalog_reason(cuisine: str | None, category: str | None, role: str) -> str:
    label = " · ".join(part for part in (cuisine, category) if part)
    if role == "picked":
        if label:
            return (
                f"Popular {label} dish in completed sample orders. "
                "This is not a stored personal suggestion for this customer."
            )
        return "Popular in completed sample orders because this customer has no matching stored dish rank."
    if role == "similar":
        if label:
            return (
                f"Popular {label} dish in the sample catalog. "
                "This is not based on this customer's most-ordered cuisine."
            )
        return "Popular sample dish shown because no cuisine-history match was available."
    if role == "explore":
        if label:
            return (
                f"Popular {label} dish in the sample catalog. "
                "This is not treated as a new cuisine for this customer."
            )
        return "Popular sample dish shown because no new-cuisine alternative remained."
    if role == "restaurant":
        if cuisine:
            return (
                f"Popular {cuisine} restaurant in completed sample orders. "
                "This is not a stored personal restaurant rank."
            )
        return "Popular restaurant in completed sample orders because this customer has no matching stored restaurant rank."
    return "Popular in completed sample orders. This is not a stored personal suggestion."


def _volume_foods(
    catalog: dict[str, object],
    limit: int,
    cuisine: str | None,
    category: str | None,
    reason: str,
    fallback_kind: str,
    exclude: set[str] | None = None,
) -> list[dict[str, object]]:
    counts = _completed_item_counts([])
    foods: dict[str, dict[str, object]] = catalog["foods"]
    skip = exclude or set()
    ranked = sorted(
        ((int(counts.get(food_id, 0)), food_id) for food_id in foods),
        key=lambda item: (-item[0], item[1]),
    )
    cards: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_offerings: set[tuple[str, str]] = set()
    for count, food_id in ranked:
        if food_id in skip:
            continue
        if _skip_food_offering(catalog, food_id, seen_ids, seen_offerings):
            continue
        card = _food_card(
            catalog,
            food_id,
            reason,
            True,
            "completed_orders",
            float(count),
            int(count),
            fallback_kind,
        )
        if not _keep_food(card, cuisine, category):
            continue
        _remember_food_offering(catalog, food_id, seen_ids, seen_offerings)
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _volume_restaurants(
    catalog: dict[str, object],
    limit: int,
    cuisine: str | None,
    reason: str,
    fallback_kind: str,
) -> list[dict[str, object]]:
    counts = _completed_restaurant_counts([])
    restaurants: dict[str, dict[str, object]] = catalog["restaurants"]
    ranked = []
    for restaurant_id, place in restaurants.items():
        ranked.append((int(counts.get(restaurant_id, 0)), place.get("rating") or 0.0, restaurant_id))
    ranked.sort(key=lambda item: (-item[0], -float(item[1]), item[2]))
    cards: list[dict[str, object]] = []
    for count, _rating, restaurant_id in ranked:
        card = _restaurant_card(
            catalog,
            restaurant_id,
            reason,
            True,
            "completed_orders",
            float(count),
            count,
            fallback_kind,
        )
        if not _keep_restaurant(card, cuisine):
            continue
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _maybe_food_catalog_fallback(
    items: list[dict[str, object]],
    catalog: dict[str, object],
    limit: int,
    cuisine: str | None,
    category: str | None,
    *,
    role: str,
    allow_unfiltered: bool,
    exclude: set[str] | None = None,
) -> tuple[list[dict[str, object]], str | None]:
    if items:
        return items, None
    if not cuisine and not category and not allow_unfiltered:
        return items, None
    fallback_kind = "cuisine_catalog" if cuisine or category else "cold_start"
    filled = _volume_foods(
        catalog,
        limit,
        cuisine,
        category,
        _catalog_reason(cuisine, category, role),
        fallback_kind,
        exclude,
    )
    if not filled:
        return items, None
    return filled, fallback_kind


def _maybe_restaurant_catalog_fallback(
    items: list[dict[str, object]],
    catalog: dict[str, object],
    limit: int,
    cuisine: str | None,
    _category: str | None,
    *,
    allow_unfiltered: bool,
) -> tuple[list[dict[str, object]], str | None]:
    if items:
        return items, None
    if cuisine:
        fallback_kind = "cuisine_catalog"
    elif allow_unfiltered:
        fallback_kind = "cold_start"
    else:
        return items, None
    filled = _volume_restaurants(
        catalog,
        limit,
        cuisine,
        _catalog_reason(cuisine, None, "restaurant"),
        fallback_kind,
    )
    if not filled:
        return items, None
    return filled, fallback_kind


def _apply_catalog_fallback_metadata(
    sections: list[dict[str, object]],
    fallbacks: dict[str, str | None],
    cuisine: str | None,
    category: str | None,
) -> None:
    label = " · ".join(part for part in (cuisine, category) if part) or "the catalog"
    descriptions = {
        "picked_for_you": {
            "cuisine_catalog": (
                f"Popular {label} dishes from completed sample orders. "
                "These are not stored personal ranks for this customer."
            ),
            "cold_start": "Popular dishes across the sample. This customer has no matching stored dish rank.",
        },
        "similar_to_what_you_like": {
            "cuisine_catalog": (
                f"Popular {label} dishes from the sample catalog. "
                "This is not this customer's most-ordered cuisine match."
            ),
        },
        "restaurants_for_you": {
            "cuisine_catalog": (
                f"Popular {cuisine or 'matching'} restaurants from completed sample orders. "
                "These are not stored personal restaurant ranks."
            ),
            "cold_start": "Popular restaurants across the sample. This customer has no matching stored restaurant rank.",
        },
        "explore_something_new": {
            "cuisine_catalog": (
                f"Popular {label} dishes from the sample catalog. "
                "They are not treated as a new cuisine when this customer has already ordered it."
            ),
        },
    }
    for section in sections:
        kind = fallbacks.get(str(section["id"]))
        if not kind:
            continue
        section["fallback_kind"] = kind
        section["metric"] = "completed_orders"
        section["scope"] = "global" if kind == "cold_start" else "cuisine_catalog"
        section["explanation"] = dict(COLD_START_EXPLANATION if kind == "cold_start" else CATALOG_FALLBACK_EXPLANATION)
        section["description"] = descriptions.get(str(section["id"]), {}).get(kind, section["description"])


def _apply_empty_kinds(
    sections: list[dict[str, object]],
    unavailable: list[str],
    history: dict[str, object],
) -> None:
    joined = " ".join(unavailable)
    purchased = history.get("purchased_foods") or set()
    primary = (history.get("summary") or {}).get("primary_cuisine")
    for section in sections:
        if section["items"]:
            section["empty_kind"] = None
            continue
        source = SECTION_SOURCES.get(str(section["id"]))
        if source and source in joined:
            section["empty_kind"] = "missing_data"
            section["empty_message"] = MISSING_EMPTY.get(str(section["id"]), section["empty_message"])
        elif section["id"] == "similar_to_what_you_like" and not primary:
            section["empty_kind"] = "no_history"
        elif section["id"] == "frequently_bought_together" and not purchased:
            section["empty_kind"] = "no_history"
        else:
            section["empty_kind"] = "no_results"


def _available_cuisines(items: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        cuisine = item.get("cuisine")
        if cuisine is None or analytics._missing(cuisine):
            continue
        key = _norm(cuisine)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(str(cuisine))
    names.sort()
    return names


def _annotate_filter_context(
    section: dict[str, object],
    unfiltered: list[dict[str, object]],
    cuisine: str | None,
    category: str | None,
) -> None:
    """Attach unfiltered context. Does not change ranked items or scores."""
    section["unfiltered_count"] = len(unfiltered)
    section["available_cuisines"] = _available_cuisines(unfiltered)
    if section.get("items"):
        return
    if section.get("empty_kind") in {"missing_data", "no_history"}:
        return
    if unfiltered and (cuisine or category):
        section["empty_kind"] = "filter_miss"


def _catalog(unavailable: list[str]) -> dict[str, object]:
    frames = discovery_operational.operational_frames()
    if frames is None:
        foods = _optional("food_items.parquet", ["id", "restaurant_id", "name", "category", "price"], unavailable)
        restaurants = _optional("restaurants.parquet", ["id", "name", "cuisine_type", "location_id"], unavailable)
        locations = _optional("locations.parquet", ["id", "city"], unavailable)
    else:
        foods = frames["foods"]
        restaurants = frames["restaurants"]
        locations = frames["locations"]
    features = _optional("restaurant_features.parquet", ["restaurant_id", "avg_rating", "review_volume", "order_volume"], unavailable)
    sentiment = _optional("sentiment_by_restaurant.parquet", ["restaurant_id", "review_count", "positive_count", "mean_score"], unavailable)
    food_map: dict[str, dict[str, object]] = {}
    restaurant_map: dict[str, dict[str, object]] = {}
    city_map = {str(row["id"]): None if analytics._missing(row.get("city")) else str(row["city"]) for row in locations.to_dict("records")} if not locations.empty else {}
    feature_map = {str(row["restaurant_id"]): row for row in features.to_dict("records")} if not features.empty else {}
    sentiment_map = {str(row["restaurant_id"]): row for row in sentiment.to_dict("records")} if not sentiment.empty else {}
    for row in restaurants.to_dict("records"):
        restaurant_id = str(row["id"])
        feature = feature_map.get(restaurant_id, {})
        sent = sentiment_map.get(restaurant_id, {})
        restaurant_map[restaurant_id] = {
            "id": restaurant_id,
            "name": None if analytics._missing(row.get("name")) else str(row["name"]),
            "cuisine": None if analytics._missing(row.get("cuisine_type")) else str(row["cuisine_type"]),
            "city": city_map.get(str(row.get("location_id"))) if not analytics._missing(row.get("location_id")) else None,
            "rating": analytics._json_value(feature.get("avg_rating")),
            "rating_label": RATING_LABEL if not analytics._missing(feature.get("avg_rating")) else None,
            "review_count": analytics._json_value(sent.get("review_count") if sent else feature.get("review_volume")),
            "positive_count": analytics._json_value(sent.get("positive_count")),
            "mean_sentiment": analytics._json_value(sent.get("mean_score")),
        }
    for row in foods.to_dict("records"):
        food_id = str(row["id"])
        restaurant_id = None if analytics._missing(row.get("restaurant_id")) else str(row["restaurant_id"])
        place = restaurant_map.get(restaurant_id or "", {})
        food_map[food_id] = {
            "id": food_id,
            "name": None if analytics._missing(row.get("name")) else str(row["name"]),
            "category": None if analytics._missing(row.get("category")) else str(row["category"]),
            "price": analytics._json_value(row.get("price")),
            "restaurant_id": restaurant_id,
            "restaurant_name": place.get("name"),
            "cuisine": place.get("cuisine"),
            "rating": place.get("rating"),
            "rating_label": place.get("rating_label"),
            "review_count": place.get("review_count"),
            "city": place.get("city"),
        }
    cuisines = sorted({str(place["cuisine"]) for place in restaurant_map.values() if place.get("cuisine")})
    categories = sorted({str(item["category"]) for item in food_map.values() if item.get("category")})
    cuisine_categories: dict[str, set[str]] = {}
    for item in food_map.values():
        cuisine = item.get("cuisine")
        category = item.get("category")
        if cuisine and category:
            cuisine_categories.setdefault(str(cuisine), set()).add(str(category))
    return {
        "foods": food_map,
        "restaurants": restaurant_map,
        "cuisines": cuisines,
        "categories": categories,
        "cuisine_categories": {name: sorted(values) for name, values in sorted(cuisine_categories.items())},
    }


def _history(customer_id: str, catalog: dict[str, object], unavailable: list[str]) -> dict[str, object]:
    frames = discovery_operational.operational_frames()
    if frames is None:
        orders = _optional("orders.parquet", ["id", "customer_id", "restaurant_id", "status"], unavailable)
        items = _optional("order_items.parquet", ["order_id", "food_item_id"], unavailable)
    else:
        orders = frames["orders"]
        items = frames["items"]
    if orders.empty:
        return _empty_history(customer_id)
    completed = analytics._completed(orders)
    mine = completed.loc[completed["customer_id"].map(_token) == customer_id]
    order_ids = {token for token in mine["id"].map(_token) if token}
    purchased_foods: list[str] = []
    if not items.empty and order_ids:
        lines = items.loc[items["order_id"].map(_token).isin(order_ids)]
        purchased_foods = [str(value) for value in lines["food_item_id"].dropna().map(_token) if value]
    restaurant_ids = [str(value) for value in mine["restaurant_id"].dropna().map(_token) if value]
    foods: dict[str, dict[str, object]] = catalog["foods"]
    restaurants: dict[str, dict[str, object]] = catalog["restaurants"]
    cuisine_counts: dict[str, int] = {}
    for restaurant_id in restaurant_ids:
        cuisine = restaurants.get(restaurant_id, {}).get("cuisine")
        if cuisine:
            cuisine_counts[str(cuisine)] = cuisine_counts.get(str(cuisine), 0) + 1
    primary = None
    if cuisine_counts:
        primary = sorted(cuisine_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    order_count = int(len(order_ids))
    return {
        "customer_id": customer_id,
        "order_ids": order_ids,
        "purchased_foods": set(purchased_foods),
        "purchased_restaurants": set(restaurant_ids),
        "cuisine_counts": cuisine_counts,
        "primary_cuisine": primary,
        "summary": {
            "completed_orders": order_count,
            "distinct_foods": len(set(purchased_foods)),
            "cuisines": sorted(cuisine_counts),
            "thin_history": order_count <= THIN_HISTORY_ORDERS,
            "primary_cuisine": primary,
        },
        "foods": foods,
    }


def _empty_history(customer_id: str) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "order_ids": set(),
        "purchased_foods": set(),
        "purchased_restaurants": set(),
        "cuisine_counts": {},
        "primary_cuisine": None,
        "summary": {
            "completed_orders": 0,
            "distinct_foods": 0,
            "cuisines": [],
            "thin_history": True,
            "primary_cuisine": None,
        },
    }


def _picked_for_you(
    customer_id: str,
    catalog: dict[str, object],
    history: dict[str, object],
    limit: int,
    unavailable: list[str],
    cuisine: str | None = None,
    category: str | None = None,
) -> list[dict[str, object]]:
    frame = _optional(
        "food_recommendations.parquet",
        ["customer_id", "food_item_id", "restaurant_id", "recommendation_score", "rank", "reason"],
        unavailable,
    )
    if frame.empty:
        return []
    rows = frame.loc[frame["customer_id"].map(_token) == customer_id].sort_values(["rank", "food_item_id"], kind="mergesort")
    cards: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_offerings: set[tuple[str, str]] = set()
    for record in rows.to_dict("records"):
        food_id = _token(record.get("food_item_id"))
        if _skip_food_offering(catalog, food_id, seen_ids, seen_offerings):
            continue
        reason, fallback = plain_reason(record.get("reason"), "food")
        fallback_kind = None
        if history["summary"]["thin_history"]:
            fallback = True
            fallback_kind = "thin_history"
            if record.get("reason") == "general pick for limited history":
                reason = FOOD_REASON_COPY["general pick for limited history"]
            else:
                reason = f"{reason}. Your completed-order history is still thin, so this is a stored fallback rank."
        card = _food_card(
            catalog,
            food_id,
            reason,
            fallback,
            "stored_rank",
            analytics._json_value(record.get("recommendation_score")),
            analytics._json_value(record.get("rank")),
            fallback_kind,
        )
        if not _keep_food(card, cuisine, category):
            continue
        _remember_food_offering(catalog, food_id, seen_ids, seen_offerings)
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _popular(
    catalog: dict[str, object],
    limit: int,
    unavailable: list[str],
    cuisine: str | None = None,
    category: str | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    counts = _completed_item_counts(unavailable)
    restaurant_counts = _completed_restaurant_counts(unavailable)
    foods: dict[str, dict[str, object]] = catalog["foods"]
    food_cards: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_offerings: set[tuple[str, str]] = set()
    food_ids = foods if cuisine or category else counts
    ranked_foods = sorted(
        ((int(counts.get(food_id, 0)), food_id) for food_id in food_ids),
        key=lambda item: (-item[0], item[1]),
    )
    for count, food_id in ranked_foods:
        if _skip_food_offering(catalog, food_id, seen_ids, seen_offerings):
            continue
        card = _food_card(
            catalog,
            food_id,
            "Popular across all customers in the completed-order data",
            False,
            "completed_orders",
            float(count),
            int(count),
        )
        if not _keep_food(card, cuisine, category):
            continue
        _remember_food_offering(catalog, food_id, seen_ids, seen_offerings)
        food_cards.append(card)
        if len(food_cards) >= limit:
            break
    restaurant_cards: list[dict[str, object]] = []
    restaurants: dict[str, dict[str, object]] = catalog["restaurants"]
    ranked = []
    for restaurant_id, place in restaurants.items():
        ranked.append((int(restaurant_counts.get(restaurant_id, 0)), place.get("rating") or 0.0, restaurant_id))
    ranked.sort(key=lambda item: (-item[0], -float(item[1]), item[2]))
    for count, _rating, restaurant_id in ranked:
        card = _restaurant_card(
            catalog,
            restaurant_id,
            "Popular across all customers in the completed-order data",
            False,
            "completed_orders",
            float(count),
            count,
        )
        if not _keep_restaurant(card, cuisine):
            continue
        restaurant_cards.append(card)
        if len(restaurant_cards) >= limit:
            break
    return food_cards, restaurant_cards


def _similar(
    catalog: dict[str, object],
    history: dict[str, object],
    picked: list[dict[str, object]],
    limit: int,
    cuisine_filter: str | None = None,
    category: str | None = None,
) -> list[dict[str, object]]:
    cuisine = history["summary"]["primary_cuisine"]
    if not cuisine:
        return []
    purchased = history["purchased_foods"]
    picked_ids = {item["id"] for item in picked}
    counts = _completed_item_counts([])
    foods: dict[str, dict[str, object]] = catalog["foods"]
    ranked = [
        (-int(counts.get(food_id, 0)), food_id)
        for food_id, item in foods.items()
        if item.get("cuisine") == cuisine and food_id not in purchased and food_id not in picked_ids
    ]
    ranked.sort()
    cards: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_offerings: set[tuple[str, str]] = set()
    for _score, food_id in ranked:
        if _skip_food_offering(catalog, food_id, seen_ids, seen_offerings):
            continue
        card = _food_card(
            catalog,
            food_id,
            f"Based on your {cuisine} orders",
            False,
            "cuisine",
            float(counts.get(food_id, 0)),
            int(counts.get(food_id, 0)),
        )
        if not _keep_food(card, cuisine_filter, category):
            continue
        _remember_food_offering(catalog, food_id, seen_ids, seen_offerings)
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _bought_together(
    customer_id: str,
    catalog: dict[str, object],
    history: dict[str, object],
    limit: int,
    min_support_count: int,
    min_confidence: float,
    min_lift: float,
    unavailable: list[str],
    cuisine: str | None = None,
    category: str | None = None,
) -> list[dict[str, object]]:
    frame = _optional(
        "association_rules.parquet",
        ["antecedent_ids", "antecedent_names", "consequent_ids", "consequent_names", "support", "confidence", "lift", "support_count"],
        unavailable,
    )
    purchased = history["purchased_foods"]
    if frame.empty or not purchased:
        return []
    cards: list[dict[str, object]] = []
    seen: set[str] = set()
    seen_offerings: set[tuple[str, str]] = set()
    ranked = []
    for record in frame.to_dict("records"):
        support_count = analytics._json_value(record.get("support_count"))
        confidence = analytics._json_value(record.get("confidence"))
        lift = analytics._json_value(record.get("lift"))
        if support_count is None or int(support_count) < min_support_count:
            continue
        if confidence is None or float(confidence) < min_confidence:
            continue
        if lift is None or float(lift) < min_lift:
            continue
        antecedent = _token(record.get("antecedent_ids"))
        consequent = _token(record.get("consequent_ids"))
        if not antecedent or not consequent or "," in antecedent or "," in consequent:
            continue
        if antecedent not in purchased or consequent in purchased:
            continue
        ranked.append((-float(lift), -float(confidence), -int(support_count), consequent, record))
    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    for _lift, _confidence, _support, consequent, record in ranked:
        if _skip_food_offering(catalog, consequent, seen, seen_offerings):
            continue
        antecedent_name = record.get("antecedent_names") or "a dish you ordered"
        card = _food_card(
            catalog,
            consequent,
            f"Often bought with {antecedent_name}. Association is not causation.",
            False,
            "lift",
            analytics._json_value(record.get("lift")),
            analytics._json_value(record.get("support_count")),
        )
        card["lift"] = analytics._json_value(record.get("lift"))
        card["confidence"] = analytics._json_value(record.get("confidence"))
        card["support"] = analytics._json_value(record.get("support"))
        card["support_count"] = analytics._json_value(record.get("support_count"))
        if not _keep_food(card, cuisine, category):
            continue
        _remember_food_offering(catalog, consequent, seen, seen_offerings)
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _restaurants_for_you(
    customer_id: str,
    catalog: dict[str, object],
    history: dict[str, object],
    limit: int,
    unavailable: list[str],
    cuisine: str | None = None,
    _category: str | None = None,
) -> list[dict[str, object]]:
    frame = _optional(
        "restaurant_recommendations.parquet",
        ["customer_id", "restaurant_id", "recommendation_score", "rank", "reason"],
        unavailable,
    )
    if frame.empty:
        return []
    rows = frame.loc[frame["customer_id"].map(_token) == customer_id].sort_values(["rank", "restaurant_id"], kind="mergesort")
    cards: list[dict[str, object]] = []
    seen: set[str] = set()
    for record in rows.to_dict("records"):
        restaurant_id = _token(record.get("restaurant_id"))
        if not restaurant_id or restaurant_id in seen:
            continue
        seen.add(restaurant_id)
        reason, fallback = plain_reason(record.get("reason"), "restaurant")
        fallback_kind = None
        if history["summary"]["thin_history"]:
            fallback = True
            fallback_kind = "thin_history"
        card = _restaurant_card(
            catalog,
            restaurant_id,
            reason,
            fallback,
            "stored_rank",
            analytics._json_value(record.get("recommendation_score")),
            analytics._json_value(record.get("rank")),
            fallback_kind,
        )
        if not _keep_restaurant(card, cuisine):
            continue
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _explore(
    catalog: dict[str, object],
    history: dict[str, object],
    used_foods: set[str],
    limit: int,
    cuisine_filter: str | None = None,
    category: str | None = None,
) -> list[dict[str, object]]:
    known = set(history["cuisine_counts"])
    purchased = history["purchased_foods"]
    counts = _completed_item_counts([])
    ranked = []
    foods: dict[str, dict[str, object]] = catalog["foods"]
    for food_id, item in foods.items():
        item_cuisine = item.get("cuisine")
        if food_id in purchased or food_id in used_foods:
            continue
        if known and item_cuisine in known:
            continue
        ranked.append((-int(counts.get(food_id, 0)), food_id))
    ranked.sort()
    cards: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_offerings: set[tuple[str, str]] = set()
    for _score, food_id in ranked:
        if _skip_food_offering(catalog, food_id, seen_ids, seen_offerings):
            continue
        item_cuisine = foods.get(food_id, {}).get("cuisine")
        reason = "A supported alternative that is not in your recent orders"
        if item_cuisine:
            article = "An" if str(item_cuisine)[:1].lower() in "aeiou" else "A"
            reason = f"{article} {item_cuisine} dish that is not in your recent orders"
        card = _food_card(catalog, food_id, reason, False, "completed_orders", float(counts.get(food_id, 0)), int(counts.get(food_id, 0)))
        if not _keep_food(card, cuisine_filter, category):
            continue
        _remember_food_offering(catalog, food_id, seen_ids, seen_offerings)
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _food_card(
    catalog: dict[str, object],
    food_id: str,
    reason: str,
    fallback: bool,
    metric: str,
    score: object,
    evidence: object,
    fallback_kind: str | None = None,
) -> dict[str, object]:
    item = catalog["foods"].get(food_id, {"id": food_id})
    return {
        "id": food_id,
        "kind": "food",
        "name": item.get("name"),
        "restaurant_id": item.get("restaurant_id"),
        "restaurant_name": item.get("restaurant_name"),
        "cuisine": item.get("cuisine"),
        "category": item.get("category"),
        "price": item.get("price"),
        "rating": item.get("rating"),
        "rating_label": item.get("rating_label"),
        "rating_source": RATING_SOURCE if item.get("rating") is not None else None,
        "review_count": item.get("review_count"),
        "city": item.get("city"),
        "image_url": None,
        "reason": reason,
        "fallback": fallback,
        "fallback_kind": fallback_kind,
        "metric": metric,
        "score": analytics._json_value(score),
        "evidence": analytics._json_value(evidence),
    }


def _restaurant_card(
    catalog: dict[str, object],
    restaurant_id: str,
    reason: str,
    fallback: bool,
    metric: str,
    score: object,
    evidence: object,
    fallback_kind: str | None = None,
) -> dict[str, object]:
    place = catalog["restaurants"].get(restaurant_id, {"id": restaurant_id})
    return {
        "id": restaurant_id,
        "kind": "restaurant",
        "name": place.get("name"),
        "restaurant_id": restaurant_id,
        "restaurant_name": place.get("name"),
        "cuisine": place.get("cuisine"),
        "category": None,
        "price": None,
        "rating": place.get("rating"),
        "rating_label": place.get("rating_label"),
        "rating_source": RATING_SOURCE if place.get("rating") is not None else None,
        "review_count": place.get("review_count"),
        "city": place.get("city"),
        "image_url": None,
        "reason": reason,
        "fallback": fallback,
        "fallback_kind": fallback_kind,
        "metric": metric,
        "score": analytics._json_value(score),
        "evidence": analytics._json_value(evidence),
    }


def _completed_item_counts(unavailable: list[str]) -> dict[str, int]:
    frames = discovery_operational.operational_frames()
    if frames is None:
        orders = _optional("orders.parquet", ["id", "status"], unavailable)
        items = _optional("order_items.parquet", ["order_id", "food_item_id"], unavailable)
    else:
        orders = frames["orders"]
        items = frames["items"]
    if orders.empty or items.empty:
        return {}
    completed_ids = set(analytics._completed(orders)["id"].map(_token))
    lines = items.loc[items["order_id"].map(_token).isin(completed_ids)]
    counts: dict[str, int] = {}
    for food_id in lines["food_item_id"].map(_token):
        if food_id:
            counts[food_id] = counts.get(food_id, 0) + 1
    return counts


def _completed_restaurant_counts(unavailable: list[str]) -> dict[str, int]:
    frames = discovery_operational.operational_frames()
    if frames is None:
        orders = _optional("orders.parquet", ["id", "status", "restaurant_id"], unavailable)
    else:
        orders = frames["orders"]
    if orders.empty:
        return {}
    counts: dict[str, int] = {}
    for restaurant_id in analytics._completed(orders)["restaurant_id"].map(_token):
        if restaurant_id:
            counts[restaurant_id] = counts.get(restaurant_id, 0) + 1
    return counts


def _filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"all", "*"}:
        return None
    return text


def _norm(value: object) -> str:
    if analytics._missing(value):
        return ""
    return str(value).strip().lower()


def _food_offering_key(catalog: dict[str, object], food_id: str) -> tuple[str, str] | None:
    """Return a (name, restaurant_id) key when both exist.

    Identical names at the same restaurant are one offering. The same dish name
    at a different restaurant is a different menu row and is not collapsed.
    Rows without a name or restaurant_id are keyed only by food_item_id.
    """
    item = catalog.get("foods", {}).get(food_id, {})
    name = _norm(item.get("name"))
    restaurant = _norm(item.get("restaurant_id"))
    if not name or not restaurant:
        return None
    return (name, restaurant)


def _skip_food_offering(
    catalog: dict[str, object],
    food_id: str | None,
    seen_ids: set[str],
    seen_offerings: set[tuple[str, str]],
) -> bool:
    if not food_id or food_id in seen_ids:
        return True
    key = _food_offering_key(catalog, food_id)
    return bool(key and key in seen_offerings)


def _remember_food_offering(
    catalog: dict[str, object],
    food_id: str | None,
    seen_ids: set[str],
    seen_offerings: set[tuple[str, str]],
) -> None:
    if not food_id:
        return
    seen_ids.add(food_id)
    key = _food_offering_key(catalog, food_id)
    if key:
        seen_offerings.add(key)


def _keep_food(card: dict[str, object], cuisine: str | None, category: str | None) -> bool:
    if cuisine and _norm(card.get("cuisine")) != _norm(cuisine):
        return False
    if category and _norm(card.get("category")) != _norm(category):
        return False
    return True


def _keep_restaurant(card: dict[str, object], cuisine: str | None) -> bool:
    if cuisine and _norm(card.get("cuisine")) != _norm(cuisine):
        return False
    return True


def _optional(filename: str, columns: list[str], unavailable: list[str]):
    try:
        return analytics._read(filename, columns)
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
        import pandas as pd

        return pd.DataFrame(columns=columns)


def _token(value: object) -> str | None:
    if analytics._missing(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text
