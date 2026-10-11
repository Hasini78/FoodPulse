"""Temporal holdout for recommendation coverage and ranking metrics.

Preferences come from completed orders before each customer's last order.
The last order is the target. Association rules are not used here, because
the stored rules were mined from the full order history and would leak future
co-purchases into the score.
"""

from __future__ import annotations

import pandas as pd

from mining.recommendation.candidates import context_as_of, prepare_recommendation_inputs
from mining.recommendation.ranker import recommend


def evaluate_holdout(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    foods: pd.DataFrame,
    restaurants: pd.DataFrame,
    reviews: pd.DataFrame,
    sentiment: pd.DataFrame,
    reference_date,
    food_k: int,
    restaurant_k: int,
) -> dict[str, object]:
    """Score later completed orders from earlier history only."""
    prepared = orders.copy()
    prepared["order_id"] = prepared["id"].map(_token)
    prepared["customer_id"] = prepared["customer_id"].map(_token)
    prepared["restaurant_id"] = prepared["restaurant_id"].map(_token)
    prepared["order_timestamp"] = pd.to_datetime(prepared["order_date"], utc=True, format="mixed", errors="coerce")
    prepared["status_norm"] = prepared["status"].astype("string").str.strip().str.lower()
    completed = prepared.loc[(prepared["status_norm"] == "completed") & prepared["order_timestamp"].notna() & prepared["order_id"].notna()]
    food_hits: list[float] = []
    food_precision: list[float] = []
    food_recall: list[float] = []
    restaurant_hits: list[float] = []
    restaurant_precision: list[float] = []
    restaurant_recall: list[float] = []
    eligible_food = 0
    eligible_restaurant = 0
    skipped = 0
    prepared = prepare_recommendation_inputs(customers, orders, order_items, foods, restaurants, reviews, sentiment)
    no_rules = pd.DataFrame(columns=["antecedent_id", "consequent_id", "restaurant_id", "confidence", "lift", "support", "association_strength"])
    catalog_ids = set(foods["id"].map(_token))
    item_lines = order_items.copy()
    item_lines["order_id"] = item_lines["order_id"].map(_token)
    item_lines["food_item_id"] = item_lines["food_item_id"].map(_token)
    items_by_order = {
        order_id: set(group["food_item_id"])
        for order_id, group in item_lines.dropna(subset=["order_id", "food_item_id"]).groupby("order_id", sort=False)
    }
    for customer_id, group in completed.groupby("customer_id"):
        ordered = group.sort_values(["order_timestamp", "order_id"])
        if len(ordered) < 2:
            skipped += 1
            continue
        test = ordered.iloc[-1]
        cutoff = test["order_timestamp"] - pd.Timedelta(seconds=1)
        context = context_as_of(prepared, cutoff, customer_id=str(customer_id))
        context["customers"] = pd.DataFrame({"customer_id": [str(customer_id)]})
        food, restaurants_out = recommend(context, no_rules, food_k, restaurant_k)
        grouped = context["purchases_by_customer"]
        mine = grouped.get(str(customer_id), context["purchases"].iloc[0:0])
        already = set(mine["food_item_id"]) if not mine.empty else set()
        targets = {item for item in items_by_order.get(str(test["order_id"]), set()) if item in catalog_ids and item not in already}
        if targets:
            eligible_food += 1
            recommended = set(food["food_item_id"]) if not food.empty else set()
            hits = len(targets & recommended)
            food_hits.append(1.0 if hits else 0.0)
            food_precision.append(hits / food_k)
            food_recall.append(hits / len(targets))
        train_restaurants = set(mine["restaurant_id"]) if not mine.empty else set()
        test_restaurant = _token(test["restaurant_id"])
        if test_restaurant and test_restaurant not in train_restaurants:
            eligible_restaurant += 1
            recommended_restaurants = set(restaurants_out["restaurant_id"]) if not restaurants_out.empty else set()
            hit = 1.0 if test_restaurant in recommended_restaurants else 0.0
            restaurant_hits.append(hit)
            restaurant_precision.append(hit / restaurant_k)
            restaurant_recall.append(hit)
    return {
        "method": "Leave the last completed order out. Earlier completed orders form the preference profile. Reviews after that cutoff are excluded.",
        "association_in_holdout": False,
        "association_note": "Stored association rules are mined from all completed orders, so they are omitted from the holdout to avoid future leakage.",
        "food_k": food_k,
        "restaurant_k": restaurant_k,
        "customers_with_one_completed_order": skipped,
        "food_eligible_customers": eligible_food,
        "restaurant_eligible_customers": eligible_restaurant,
        "food_precision_at_k": _mean(food_precision),
        "food_recall_at_k": _mean(food_recall),
        "food_hit_rate_at_k": _mean(food_hits),
        "restaurant_precision_at_k": _mean(restaurant_precision),
        "restaurant_recall_at_k": _mean(restaurant_recall),
        "restaurant_hit_rate_at_k": _mean(restaurant_hits),
        "definitions": {
            "eligible_food_customer": "At least two completed orders, and the last order contains a catalog item the customer had not bought earlier.",
            "eligible_restaurant_customer": "At least two completed orders, and the last order is at a restaurant the customer had not used earlier.",
            "hit_rate_at_k": "Share of eligible customers with at least one held-out target in the top K.",
            "precision_at_k": "Mean share of the K recommendations that are held-out targets. Restaurant precision uses one target, so a hit contributes 1/K.",
            "recall_at_k": "Mean share of held-out targets that appear in the top K.",
        },
    }


def _target_items(order_items: pd.DataFrame, foods: pd.DataFrame, order_id: str, already_bought: set[str]) -> set[str]:
    catalog = set(foods["id"].map(_token))
    lines = order_items.copy()
    lines["order_id"] = lines["order_id"].map(_token)
    lines["food_item_id"] = lines["food_item_id"].map(_token)
    targets = set(lines.loc[lines["order_id"] == order_id, "food_item_id"])
    return {item for item in targets if item in catalog and item not in already_bought}


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _token(value: object) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text or None
    if number.is_integer():
        return str(int(number))
    return text
