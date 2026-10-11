"""Catalog, history, and recommendation candidates.

Food items stay tied to the restaurant that sells them. Association rules are
an optional input. A missing rule file does not stop recommendations.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import pandas as pd

from etl.transform.feature_engineering import end_of_reference_day
from etl.transform.parsing import parse_timestamps

logger = logging.getLogger(__name__)

LIFT_CAP = 5.0
CUISINE_LIMIT = 2
CUISINE_ITEM_LIMIT = 40
COLD_RESTAURANT_LIMIT = 10
COLD_ITEMS_PER_RESTAURANT = 2


def load_association_rules(path, foods: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return usable one-to-one rules and any data-quality warnings."""
    warnings: list[str] = []
    empty = _empty_rules()
    if path is None or not path.is_file():
        warnings.append(
            "Association rules were not found. Generate them with "
            "python -m mining.association.run_mining --min-support 0.003 --min-confidence 0.3. "
            "Recommendations continue without the association signal."
        )
        return empty, warnings
    rules = pd.read_parquet(path)
    required = {"antecedent_ids", "consequent_ids", "confidence", "lift", "support"}
    missing = sorted(required.difference(rules.columns))
    if missing:
        warnings.append(f"Association rules are missing columns: {', '.join(missing)}. The association signal was skipped.")
        return empty, warnings
    catalog = foods.loc[:, ["id", "restaurant_id"]].copy()
    catalog["item_id"] = catalog["id"].map(_token)
    catalog["restaurant_id"] = catalog["restaurant_id"].map(_token)
    catalog = catalog.dropna(subset=["item_id", "restaurant_id"]).drop_duplicates("item_id")
    lookup = catalog.set_index("item_id")["restaurant_id"]
    kept: list[dict[str, object]] = []
    dropped = 0
    for rule in rules.itertuples(index=False):
        antecedent = _single_id(getattr(rule, "antecedent_ids"))
        consequent = _single_id(getattr(rule, "consequent_ids"))
        if antecedent is None or consequent is None or antecedent not in lookup or consequent not in lookup:
            dropped += 1
            continue
        if lookup.at[antecedent] != lookup.at[consequent]:
            dropped += 1
            continue
        confidence = float(rule.confidence)
        lift = float(rule.lift)
        support = float(rule.support)
        if confidence <= 0 or lift < 1:
            dropped += 1
            continue
        kept.append(
            {
                "antecedent_id": antecedent,
                "consequent_id": consequent,
                "restaurant_id": lookup.at[consequent],
                "confidence": confidence,
                "lift": lift,
                "support": support,
                "association_strength": 0.5 * min(confidence, 1.0) + 0.5 * min(lift, LIFT_CAP) / LIFT_CAP,
            }
        )
    if dropped:
        warnings.append(f"{dropped} association rules were skipped because an item was missing, crossed restaurants, or had lift below 1.")
    frame = pd.DataFrame(kept) if kept else empty
    logger.info("Loaded %s usable association rules", len(frame))
    return frame, warnings


def prepare_recommendation_inputs(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    foods: pd.DataFrame,
    restaurants: pd.DataFrame,
    reviews: pd.DataFrame,
    sentiment: pd.DataFrame,
) -> dict[str, object]:
    """Parse each source once so later cutoffs only filter these tables."""
    _require(customers, ("customer_id",), "customers")
    _require(orders, ("id", "customer_id", "restaurant_id", "status", "order_date"), "orders")
    _require(order_items, ("order_id", "food_item_id"), "order items")
    _require(foods, ("id", "restaurant_id", "is_available"), "food items")
    _require(restaurants, ("id", "cuisine_type", "is_active"), "restaurants")
    _require(reviews, ("id", "customer_id", "restaurant_id", "rating", "created_at"), "reviews")
    _require(sentiment, ("review_id", "overall_score"), "review sentiment")
    people = customers.drop_duplicates("customer_id").loc[:, ["customer_id"]].copy()
    people["customer_id"] = people["customer_id"].map(_token)
    catalog = _catalog(foods, restaurants)
    lines, line_issues = _purchase_lines(orders, order_items, catalog)
    review_rows = _review_rows(reviews, sentiment)
    return {
        "customers": people.dropna(subset=["customer_id"]),
        "catalog": catalog,
        "static": _static_menu(catalog),
        "lines": lines,
        "line_issues": line_issues,
        "review_rows": review_rows,
    }


def context_as_of(prepared: dict[str, object], cutoff: pd.Timestamp, customer_id: str | None = None) -> dict[str, object]:
    """Build one cutoff's catalog lookups from tables parsed earlier."""
    lines: pd.DataFrame = prepared["lines"]
    scoped = lines.loc[lines["order_timestamp"] <= cutoff] if not lines.empty else lines
    purchases = _with_purchase_counts(scoped)
    quality = _quality_from_rows(prepared["review_rows"], prepared["catalog"], cutoff)
    purchases = attach_customer_ratings(purchases, quality)
    warnings = _warnings_as_of(prepared["line_issues"], cutoff)
    return _indexed_context(prepared["customers"], prepared["catalog"], prepared["static"], purchases, quality, warnings, cutoff, customer_id)


def build_context(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    foods: pd.DataFrame,
    restaurants: pd.DataFrame,
    reviews: pd.DataFrame,
    sentiment: pd.DataFrame,
    reference_date: date,
    as_of: pd.Timestamp | None = None,
) -> dict[str, object]:
    """Prepare catalog, history, and quality tables for one cutoff."""
    prepared = prepare_recommendation_inputs(customers, orders, order_items, foods, restaurants, reviews, sentiment)
    cutoff = as_of if as_of is not None else end_of_reference_day(reference_date)
    return context_as_of(prepared, cutoff)


def food_candidates(context: dict[str, object], rules: pd.DataFrame, customer_id: str) -> pd.DataFrame:
    """Return distinct food candidates for one customer."""
    rule_rows = [] if rules.empty else list(zip(rules["antecedent_id"].astype(str), rules["consequent_id"].astype(str)))
    rows = food_candidate_rows(context, rule_rows, customer_id)
    return pd.DataFrame(rows)


def food_candidate_rows(context: dict[str, object], rule_rows: list[tuple], customer_id: str) -> list[dict[str, object]]:
    """Return food candidates without building a DataFrame."""
    mine = _customer_purchases(context, customer_id)
    bought = set(mine["food_item_id"]) if not mine.empty else set()
    repeats = set(mine.loc[mine["purchase_count"] >= 2, "food_item_id"]) if not mine.empty else set()
    lookup: dict[str, dict[str, object]] = context["item_lookup"]
    rows: list[dict[str, object]] = []
    seen: set[str] = set()

    def add(item_id: str, source: str) -> None:
        if item_id in seen:
            return
        item = lookup.get(item_id)
        if item is None:
            return
        if item_id in bought and item_id not in repeats:
            return
        seen.add(item_id)
        rows.append(
            {
                "customer_id": customer_id,
                "food_item_id": item_id,
                "restaurant_id": item["restaurant_id"],
                "cuisine_type": item["cuisine_type"],
                "source": source,
                "repeat_item": item_id in repeats,
            }
        )

    if rule_rows and not mine.empty:
        for rule in rule_rows:
            if rule[0] in bought:
                add(rule[1], "association")
    if mine.empty:
        for item_id in _cold_ids(context):
            add(item_id, "cold_start")
    else:
        for item_id in _cuisine_item_ids(context, mine, bought):
            add(item_id, "cuisine")
        for item_id in repeats:
            add(item_id, "repeat")
        if mine["order_id"].nunique() <= 2:
            for item_id in _cold_ids(context):
                add(item_id, "cold_start")
    return rows


def restaurant_candidates(context: dict[str, object], customer_id: str) -> pd.DataFrame:
    """Return restaurants the customer has not used, plus highly rated repeats."""
    return pd.DataFrame(restaurant_candidate_rows(context, customer_id))


def restaurant_candidate_rows(context: dict[str, object], customer_id: str) -> list[dict[str, object]]:
    """Return restaurant candidates without building a DataFrame."""
    mine = _customer_purchases(context, customer_id)
    visited = set(mine["restaurant_id"]) if not mine.empty else set()
    ratings = mine.groupby("restaurant_id")["customer_rating"].mean() if not mine.empty else pd.Series(dtype="float64")
    rows: list[dict[str, object]] = []
    for restaurant_id, cuisine_type in context["active_restaurants"]:
        rating = ratings.get(restaurant_id, pd.NA)
        liked = restaurant_id in visited and pd.notna(rating) and float(rating) >= 4
        if restaurant_id in visited and not liked:
            continue
        rows.append(
            {
                "customer_id": customer_id,
                "restaurant_id": restaurant_id,
                "cuisine_type": cuisine_type,
                "repeat_restaurant": bool(liked),
            }
        )
    return rows


def _customer_purchases(context: dict[str, object], customer_id: str) -> pd.DataFrame:
    grouped: dict[str, pd.DataFrame] = context["purchases_by_customer"]
    found = grouped.get(customer_id)
    if found is not None:
        return found
    return context["purchases"].iloc[0:0]


def _catalog(foods: pd.DataFrame, restaurants: pd.DataFrame) -> pd.DataFrame:
    menu = foods.copy()
    menu["food_item_id"] = menu["id"].map(_token)
    menu["restaurant_id"] = menu["restaurant_id"].map(_token)
    places = restaurants.copy()
    places["restaurant_id"] = places["id"].map(_token)
    places["cuisine_type"] = places["cuisine_type"].astype("string").str.strip()
    merged = menu.merge(places.loc[:, ["restaurant_id", "cuisine_type", "is_active"]], how="left", on="restaurant_id")
    merged["is_available"] = _truthy(merged["is_available"])
    merged["is_active"] = _truthy(merged["is_active"]).fillna(False)
    return merged.dropna(subset=["food_item_id", "restaurant_id"])


def _purchase_lines(orders: pd.DataFrame, order_items: pd.DataFrame, catalog: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = orders.copy()
    working["order_id"] = working["id"].map(_token)
    working["customer_id"] = working["customer_id"].map(_token)
    working["restaurant_id"] = working["restaurant_id"].map(_token)
    working["order_timestamp"] = parse_timestamps(working["order_date"])
    working["status_norm"] = working["status"].astype("string").str.strip().str.lower()
    working = working.dropna(subset=["order_id", "customer_id", "restaurant_id", "order_timestamp"])
    working = working.drop_duplicates("order_id", keep="first")
    working = working.loc[working["status_norm"] == "completed"]
    lines = order_items.copy()
    lines["order_id"] = lines["order_id"].map(_token)
    lines["food_item_id"] = lines["food_item_id"].map(_token)
    lines = lines.dropna(subset=["order_id", "food_item_id"]).drop_duplicates(["order_id", "food_item_id"])
    known = catalog.loc[:, ["food_item_id", "restaurant_id", "cuisine_type"]].drop_duplicates("food_item_id")
    joined = lines.merge(working, on="order_id", how="inner").merge(known, on="food_item_id", how="left", suffixes=("_order", "_item"))
    mismatched = joined["restaurant_id_item"].notna() & (joined["restaurant_id_order"] != joined["restaurant_id_item"])
    unknown = joined["restaurant_id_item"].isna()
    issues = pd.DataFrame({"order_timestamp": joined["order_timestamp"], "mismatch": mismatched.to_numpy(), "unknown": unknown.to_numpy()})
    issues = issues.loc[issues["mismatch"] | issues["unknown"]]
    clean = joined.loc[~mismatched & ~unknown].copy()
    empty = pd.DataFrame(columns=["customer_id", "food_item_id", "restaurant_id", "cuisine_type", "order_id", "order_timestamp"])
    if clean.empty:
        return empty, issues
    clean["restaurant_id"] = clean["restaurant_id_order"]
    return clean.loc[:, ["customer_id", "food_item_id", "restaurant_id", "cuisine_type", "order_id", "order_timestamp"]], issues


def _warnings_as_of(issues: pd.DataFrame, cutoff: pd.Timestamp) -> list[str]:
    if issues.empty:
        return []
    scoped = issues.loc[issues["order_timestamp"] <= cutoff]
    warnings: list[str] = []
    mismatch = int(scoped["mismatch"].sum())
    unknown = int(scoped["unknown"].sum())
    if mismatch:
        warnings.append(f"{mismatch} order lines were skipped because the food item belongs to another restaurant.")
    if unknown:
        warnings.append(f"{unknown} order lines were skipped because the food item id is not in the catalog.")
    return warnings


def _with_purchase_counts(lines: pd.DataFrame) -> pd.DataFrame:
    columns = ["customer_id", "food_item_id", "restaurant_id", "cuisine_type", "order_id", "order_timestamp", "purchase_count", "customer_rating"]
    if lines.empty:
        return pd.DataFrame(columns=columns)
    counts = lines.groupby(["customer_id", "food_item_id"], as_index=False).size().rename(columns={"size": "purchase_count"})
    counted = lines.merge(counts, on=["customer_id", "food_item_id"], how="left")
    counted["customer_rating"] = pd.NA
    return counted.loc[:, columns]


def _review_rows(reviews: pd.DataFrame, sentiment: pd.DataFrame) -> pd.DataFrame:
    unique_reviews = reviews.drop_duplicates("id").copy()
    unique_reviews["review_id"] = unique_reviews["id"].map(_token)
    unique_reviews["restaurant_id"] = unique_reviews["restaurant_id"].map(_token)
    unique_reviews["customer_id"] = unique_reviews["customer_id"].map(_token)
    unique_reviews["created_at"] = parse_timestamps(unique_reviews["created_at"])
    unique_reviews["rating"] = pd.to_numeric(unique_reviews["rating"], errors="coerce")
    unique_reviews = unique_reviews.loc[unique_reviews["created_at"].notna()]
    scores = sentiment.drop_duplicates("review_id").copy()
    scores["review_id"] = scores["review_id"].map(_token)
    scores["overall_score"] = pd.to_numeric(scores["overall_score"], errors="coerce")
    return unique_reviews.merge(scores.loc[:, ["review_id", "overall_score"]], on="review_id", how="left")


def _quality_from_rows(review_rows: pd.DataFrame, catalog: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    places = catalog.loc[:, ["restaurant_id", "cuisine_type"]].drop_duplicates("restaurant_id")
    linked = review_rows.loc[review_rows["created_at"] <= cutoff] if not review_rows.empty else review_rows
    if linked.empty:
        quality = places.copy()
        quality["mean_rating"] = pd.NA
        quality["mean_sentiment"] = pd.NA
        quality["review_count"] = 0
        quality["quality_score"] = 0.5
        quality["quality_imputed"] = True
        return quality
    grouped = linked.groupby("restaurant_id", as_index=False).agg(
        mean_rating=("rating", "mean"),
        mean_sentiment=("overall_score", "mean"),
        review_count=("review_id", "size"),
    )
    customer_ratings = linked.groupby(["customer_id", "restaurant_id"], as_index=False)["rating"].mean()
    quality = places.merge(grouped, how="left", on="restaurant_id")
    quality["quality_score"] = _vector_quality(quality["mean_rating"], quality["mean_sentiment"])
    quality["quality_imputed"] = quality["mean_rating"].isna() & quality["mean_sentiment"].isna()
    quality.attrs["customer_ratings"] = customer_ratings
    return quality


def _vector_quality(mean_rating: pd.Series, mean_sentiment: pd.Series) -> pd.Series:
    rating = (mean_rating / 5.0).clip(lower=0.0, upper=1.0)
    sentiment = ((mean_sentiment + 1.0) / 2.0).clip(lower=0.0, upper=1.0)
    rating_ok = rating.notna()
    sentiment_ok = sentiment.notna()
    score = pd.Series(0.5, index=mean_rating.index, dtype="float64")
    score = score.mask(rating_ok & ~sentiment_ok, rating)
    score = score.mask(~rating_ok & sentiment_ok, sentiment)
    score = score.mask(rating_ok & sentiment_ok, (rating + sentiment) / 2.0)
    return score


def _static_menu(catalog: pd.DataFrame) -> dict[str, object]:
    """Catalog membership that does not change with the cutoff."""
    available = catalog.loc[catalog["is_available"] & catalog["is_active"]].drop_duplicates("food_item_id", keep="first")
    cuisine_items: dict[object, list[str]] = {}
    for cuisine_type, group in available.groupby("cuisine_type", sort=False):
        cuisine_items[cuisine_type] = group["food_item_id"].astype(str).tolist()
    items_by_restaurant: dict[object, list[str]] = {}
    for restaurant_id, group in available.groupby("restaurant_id", sort=False):
        items_by_restaurant[restaurant_id] = group["food_item_id"].astype(str).tolist()
    active = catalog.loc[catalog["is_active"], ["restaurant_id", "cuisine_type"]].drop_duplicates()
    return {
        "available_items": list(zip(available["food_item_id"].astype(str), available["restaurant_id"], available["cuisine_type"])),
        "cuisine_items": cuisine_items,
        "items_by_restaurant": items_by_restaurant,
        "active_restaurants": list(zip(active["restaurant_id"], active["cuisine_type"])),
        "restaurant_ids": catalog.drop_duplicates("restaurant_id")["restaurant_id"].tolist(),
    }


def _indexed_context(customers, catalog, static, purchases, quality, warnings, cutoff, customer_id: str | None = None) -> dict[str, object]:
    quality_map = quality.set_index("restaurant_id")["quality_score"].to_dict()
    item_counts = purchases.groupby("food_item_id").size() if not purchases.empty else pd.Series(dtype="int64")
    restaurant_counts = purchases.groupby("restaurant_id")["order_id"].nunique() if not purchases.empty else pd.Series(dtype="int64")
    max_item = float(item_counts.max()) if len(item_counts) else 0.0
    max_restaurant = float(restaurant_counts.max()) if len(restaurant_counts) else 0.0
    item_lookup: dict[str, dict[str, object]] = {}
    for food_item_id, restaurant_id, cuisine_type in static["available_items"]:
        item_count = float(item_counts.get(food_item_id, 0.0))
        restaurant_count = float(restaurant_counts.get(restaurant_id, 0.0))
        quality_score = quality_map.get(restaurant_id, 0.5)
        item_lookup[food_item_id] = {
            "food_item_id": food_item_id,
            "restaurant_id": restaurant_id,
            "cuisine_type": cuisine_type,
            "quality_score": float(quality_score) if pd.notna(quality_score) else 0.5,
            "item_popularity": item_count / max_item if max_item else 0.0,
            "restaurant_popularity": restaurant_count / max_restaurant if max_restaurant else 0.0,
        }
    restaurant_lookup = {
        restaurant_id: {
            "quality_score": float(quality_map[restaurant_id]) if restaurant_id in quality_map and pd.notna(quality_map[restaurant_id]) else 0.5,
            "restaurant_popularity": (float(restaurant_counts.get(restaurant_id, 0.0)) / max_restaurant) if max_restaurant else 0.0,
        }
        for restaurant_id in static["restaurant_ids"]
    }
    if purchases.empty:
        purchases_by_customer: dict[str, pd.DataFrame] = {}
    elif customer_id is not None:
        mine = purchases.loc[purchases["customer_id"] == customer_id]
        purchases_by_customer = {customer_id: mine} if not mine.empty else {}
    else:
        purchases_by_customer = {str(person): group for person, group in purchases.groupby("customer_id", sort=False)}
    return {
        "customers": customers,
        "catalog": catalog,
        "purchases": purchases,
        "purchases_by_customer": purchases_by_customer,
        "quality": quality,
        "warnings": warnings,
        "cutoff": cutoff,
        "item_lookup": item_lookup,
        "restaurant_lookup": restaurant_lookup,
        "cuisine_items": static["cuisine_items"],
        "items_by_restaurant": static["items_by_restaurant"],
        "active_restaurants": static["active_restaurants"],
    }


def _cold_ids(context: dict[str, object]) -> list[str]:
    cached = context.get("cold_item_ids")
    if cached is not None:
        return cached
    lookup: dict[str, dict[str, object]] = context["item_lookup"]
    by_restaurant: dict[object, list[str]] = context["items_by_restaurant"]
    places = []
    for restaurant_id, item_ids in by_restaurant.items():
        quality = max(float(lookup[item_id]["quality_score"]) for item_id in item_ids)
        places.append((-quality, str(restaurant_id), restaurant_id))
    places.sort()
    chosen: list[str] = []
    for _quality, _label, restaurant_id in places[:COLD_RESTAURANT_LIMIT]:
        ordered = sorted(by_restaurant[restaurant_id], key=str)
        chosen.extend(ordered[:COLD_ITEMS_PER_RESTAURANT])
    context["cold_item_ids"] = chosen
    return chosen


def attach_customer_ratings(purchases: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    """Copy per-customer restaurant ratings onto purchase rows when reviews exist."""
    ratings = quality.attrs.get("customer_ratings")
    if ratings is None or purchases.empty:
        return purchases
    rated = purchases.drop(columns=["customer_rating"]).merge(ratings, on=["customer_id", "restaurant_id"], how="left")
    rated = rated.rename(columns={"rating": "customer_rating"})
    return rated


def _cold_item_ids(available: pd.DataFrame) -> list[str]:
    if available.empty or "quality_score" not in available.columns:
        return []
    places = available.groupby("restaurant_id", as_index=False)["quality_score"].max().sort_values(["quality_score", "restaurant_id"], ascending=[False, True])
    chosen: list[str] = []
    for restaurant_id in places["restaurant_id"].head(COLD_RESTAURANT_LIMIT):
        items = available.loc[available["restaurant_id"] == restaurant_id].sort_values("food_item_id")
        chosen.extend(items["food_item_id"].head(COLD_ITEMS_PER_RESTAURANT).tolist())
    return chosen


def _add_popularity(catalog: pd.DataFrame, purchases: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    menu = catalog.merge(quality.loc[:, ["restaurant_id", "quality_score", "quality_imputed", "mean_rating", "mean_sentiment"]], how="left", on="restaurant_id")
    menu["quality_score"] = menu["quality_score"].fillna(0.5)
    item_counts = purchases.groupby("food_item_id").size() if not purchases.empty else pd.Series(dtype="int64")
    restaurant_counts = purchases.groupby("restaurant_id")["order_id"].nunique() if not purchases.empty else pd.Series(dtype="int64")
    max_item = float(item_counts.max()) if len(item_counts) else 0.0
    max_restaurant = float(restaurant_counts.max()) if len(restaurant_counts) else 0.0
    menu["item_popularity"] = menu["food_item_id"].map(item_counts).fillna(0.0)
    menu["restaurant_popularity"] = menu["restaurant_id"].map(restaurant_counts).fillna(0.0)
    menu["item_popularity"] = menu["item_popularity"] / max_item if max_item else 0.0
    menu["restaurant_popularity"] = menu["restaurant_popularity"] / max_restaurant if max_restaurant else 0.0
    return menu


def _cuisine_item_ids(context: dict[str, object], purchases: pd.DataFrame, bought: set[str]) -> list[str]:
    counts = purchases.groupby("cuisine_type", dropna=False).size()
    if counts.empty:
        return []
    ranked = counts.reset_index()
    ranked.columns = ["cuisine_type", "orders"]
    ranked = ranked.sort_values(["orders", "cuisine_type"], ascending=[False, True], kind="mergesort")
    names = ranked["cuisine_type"].head(CUISINE_LIMIT).tolist()
    lookup: dict[str, dict[str, object]] = context["item_lookup"]
    cuisine_items: dict[str, list[str]] = context["cuisine_items"]
    pool: list[str] = []
    for name in names:
        for item_id in cuisine_items.get(name, []):
            if item_id not in bought:
                pool.append(item_id)
    pool.sort(key=lambda item_id: (-lookup[item_id]["quality_score"], str(lookup[item_id]["food_item_id"])))
    return pool[:CUISINE_ITEM_LIMIT]


def _empty_rules() -> pd.DataFrame:
    return pd.DataFrame(columns=["antecedent_id", "consequent_id", "restaurant_id", "confidence", "lift", "support", "association_strength"])


def _single_id(value: object) -> str | None:
    text = _token(value)
    if text is None or "," in text:
        return None
    return text


def _token(value: object) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def _truthy(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype("string").str.strip().str.lower().isin(["true", "1", "yes"])


def _require(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def parse_cutoff(value: str | date | datetime | None) -> date:
    """Parse the recommendation reference date."""
    from etl.transform.feature_engineering import parse_reference_date

    return parse_reference_date(value)
