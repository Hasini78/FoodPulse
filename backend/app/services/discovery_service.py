"""Netflix-style discovery rows over stored mining outputs.

This module never trains a model, never writes Parquet, and never connects to
Snowflake. Ranking scores are ranking signals, not purchase probabilities.
Association rules describe co-purchase, not causation.
"""

from __future__ import annotations

from app.services import analytics_service as analytics
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
    catalog = _catalog(unavailable)
    history = _history(identifier, catalog, unavailable)
    picked = _picked_for_you(identifier, catalog, history, limit, unavailable, cuisine_filter, category_filter)
    popular_foods, popular_restaurants = _popular(catalog, limit, unavailable, cuisine_filter, category_filter)
    similar = _similar(catalog, history, picked, limit, cuisine_filter, category_filter)
    together = _bought_together(
        identifier, catalog, history, limit, min_support_count, min_confidence, min_lift, unavailable, cuisine_filter, category_filter
    )
    restaurants = _restaurants_for_you(identifier, catalog, history, limit, unavailable, cuisine_filter, category_filter)
    used_foods = {
        item["id"]
        for item in picked + popular_foods + similar + together
        if item.get("kind") == "food"
    }
    explore = _explore(catalog, history, used_foods, limit, cuisine_filter, category_filter)
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
    _apply_empty_kinds(sections, unavailable, history)
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
    return {
        "id": section_id,
        "title": title,
        "description": description,
        "metric": metric,
        "scope": scope,
        "items": items,
        "empty_message": empty_message,
        "empty_kind": None if items else "no_results",
    }


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


def _catalog(unavailable: list[str]) -> dict[str, object]:
    foods = _optional("food_items.parquet", ["id", "restaurant_id", "name", "category", "price"], unavailable)
    restaurants = _optional("restaurants.parquet", ["id", "name", "cuisine_type", "location_id"], unavailable)
    features = _optional("restaurant_features.parquet", ["restaurant_id", "avg_rating", "review_volume", "order_volume"], unavailable)
    sentiment = _optional("sentiment_by_restaurant.parquet", ["restaurant_id", "review_count", "positive_count", "mean_score"], unavailable)
    locations = _optional("locations.parquet", ["id", "city"], unavailable)
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
    orders = _optional("orders.parquet", ["id", "customer_id", "restaurant_id", "status"], unavailable)
    items = _optional("order_items.parquet", ["order_id", "food_item_id"], unavailable)
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
        if history["summary"]["thin_history"]:
            fallback = True
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
        if history["summary"]["thin_history"]:
            fallback = True
        card = _restaurant_card(
            catalog,
            restaurant_id,
            reason,
            fallback,
            "stored_rank",
            analytics._json_value(record.get("recommendation_score")),
            analytics._json_value(record.get("rank")),
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
        "metric": metric,
        "score": analytics._json_value(score),
        "evidence": analytics._json_value(evidence),
    }


def _completed_item_counts(unavailable: list[str]) -> dict[str, int]:
    orders = _optional("orders.parquet", ["id", "status"], unavailable)
    items = _optional("order_items.parquet", ["order_id", "food_item_id"], unavailable)
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
    orders = _optional("orders.parquet", ["id", "status", "restaurant_id"], unavailable)
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
