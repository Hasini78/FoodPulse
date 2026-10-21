"""Temporal holdout for recommendation coverage and ranking metrics.

Preferences come from completed orders before each customer's last order.
The last order is the target. Association rules are not used here, because
the stored rules were mined from the full order history and would leak future
co-purchases into the score.
"""

from __future__ import annotations

import math

import pandas as pd

from mining.recommendation.candidates import context_as_of, prepare_recommendation_inputs
from mining.recommendation.ranker import DEFAULT_VARIANT, recommend

PRIMARY_METRICS = (
    "food_hit_rate_at_k",
    "restaurant_hit_rate_at_k",
    "food_ndcg_at_k",
    "restaurant_ndcg_at_k",
)


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
    variant: str = DEFAULT_VARIANT,
) -> dict[str, object]:
    """Score later completed orders from earlier history only."""
    prepared_orders = orders.copy()
    prepared_orders["order_id"] = prepared_orders["id"].map(_token)
    prepared_orders["customer_id"] = prepared_orders["customer_id"].map(_token)
    prepared_orders["restaurant_id"] = prepared_orders["restaurant_id"].map(_token)
    prepared_orders["order_timestamp"] = pd.to_datetime(
        prepared_orders["order_date"], utc=True, format="mixed", errors="coerce"
    )
    prepared_orders["status_norm"] = prepared_orders["status"].astype("string").str.strip().str.lower()
    completed = prepared_orders.loc[
        (prepared_orders["status_norm"] == "completed")
        & prepared_orders["order_timestamp"].notna()
        & prepared_orders["order_id"].notna()
    ]
    food_hits: list[float] = []
    food_precision: list[float] = []
    food_recall: list[float] = []
    food_ndcg: list[float] = []
    food_name_hits: list[float] = []
    restaurant_hits: list[float] = []
    restaurant_precision: list[float] = []
    restaurant_recall: list[float] = []
    restaurant_ndcg: list[float] = []
    eligible_food = 0
    eligible_restaurant = 0
    skipped = 0
    leaked_training_orders = 0
    prepared = prepare_recommendation_inputs(customers, orders, order_items, foods, restaurants, reviews, sentiment)
    no_rules = pd.DataFrame(
        columns=["antecedent_id", "consequent_id", "restaurant_id", "confidence", "lift", "support", "association_strength"]
    )
    catalog_ids = set(foods["id"].map(_token))
    name_map = _name_map(foods)
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
        cutoff = pd.Timestamp(test["order_timestamp"]) - pd.Timedelta(1, unit="s")
        context = context_as_of(prepared, cutoff, customer_id=str(customer_id))
        context["customers"] = pd.DataFrame({"customer_id": [str(customer_id)]})
        food, restaurants_out = recommend(context, no_rules, food_k, restaurant_k, variant=variant)
        grouped = context["purchases_by_customer"]
        mine = grouped.get(str(customer_id), context["purchases"].iloc[0:0])
        already = set(mine["food_item_id"]) if not mine.empty else set()
        if not mine.empty and str(test["order_id"]) in set(mine["order_id"].map(_token)):
            leaked_training_orders += 1
        targets = {item for item in items_by_order.get(str(test["order_id"]), set()) if item in catalog_ids and item not in already}
        if targets:
            eligible_food += 1
            recommended = _ordered_ids(food, "food_item_id")
            recommended_set = set(recommended)
            hits = len(targets & recommended_set)
            food_hits.append(1.0 if hits else 0.0)
            food_precision.append(hits / food_k)
            food_recall.append(hits / len(targets))
            food_ndcg.append(_ndcg(recommended, targets, food_k))
            target_names = {name_map.get(item) for item in targets if name_map.get(item)}
            recommended_names = {name_map.get(item) for item in recommended if name_map.get(item)}
            food_name_hits.append(1.0 if target_names and (target_names & recommended_names) else 0.0)
        train_restaurants = set(mine["restaurant_id"]) if not mine.empty else set()
        test_restaurant = _token(test["restaurant_id"])
        if test_restaurant and test_restaurant not in train_restaurants:
            eligible_restaurant += 1
            recommended_restaurants = _ordered_ids(restaurants_out, "restaurant_id")
            hit = 1.0 if test_restaurant in set(recommended_restaurants) else 0.0
            restaurant_hits.append(hit)
            restaurant_precision.append(hit / restaurant_k)
            restaurant_recall.append(hit)
            restaurant_ndcg.append(_ndcg(recommended_restaurants, {test_restaurant}, restaurant_k))
    return {
        "method": "Leave the last completed order out. Earlier completed orders form the preference profile. Reviews after that cutoff are excluded.",
        "variant": variant,
        "association_in_holdout": False,
        "association_note": "Stored association rules are mined from all completed orders, so they are omitted from the holdout to avoid future leakage.",
        "food_k": food_k,
        "restaurant_k": restaurant_k,
        "customers_with_one_completed_order": skipped,
        "food_eligible_customers": eligible_food,
        "restaurant_eligible_customers": eligible_restaurant,
        "leaked_holdout_orders_in_training": leaked_training_orders,
        "food_precision_at_k": _mean(food_precision),
        "food_recall_at_k": _mean(food_recall),
        "food_hit_rate_at_k": _mean(food_hits),
        "food_ndcg_at_k": _mean(food_ndcg),
        "food_name_hit_rate_at_k": _mean(food_name_hits),
        "restaurant_precision_at_k": _mean(restaurant_precision),
        "restaurant_recall_at_k": _mean(restaurant_recall),
        "restaurant_hit_rate_at_k": _mean(restaurant_hits),
        "restaurant_ndcg_at_k": _mean(restaurant_ndcg),
        "definitions": {
            "eligible_food_customer": "At least two completed orders, and the last order contains a catalog item the customer had not bought earlier.",
            "eligible_restaurant_customer": "At least two completed orders, and the last order is at a restaurant the customer had not used earlier.",
            "hit_rate_at_k": "Share of eligible customers with at least one held-out target in the top K. Food targets are food_item_id values, not dish names.",
            "precision_at_k": "Mean share of the K recommendations that are held-out targets. Restaurant precision uses one target, so a hit contributes 1/K.",
            "recall_at_k": "Mean share of held-out targets that appear in the top K.",
            "ndcg_at_k": "Mean binary NDCG@K using the stored rank order. Relevance is 1 if the item is a held-out target.",
            "food_name_hit_rate_at_k": "Diagnostic only. A hit if any recommended dish name matches a held-out name. Duplicate catalog names make this easier than food_item_id hit rate. It is not the primary metric.",
        },
    }


def compare_holdout(
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
    """Evaluate baseline and improved variants on the same temporal split."""
    baseline = evaluate_holdout(
        customers, orders, order_items, foods, restaurants, reviews, sentiment, reference_date, food_k, restaurant_k, variant="baseline"
    )
    improved = evaluate_holdout(
        customers, orders, order_items, foods, restaurants, reviews, sentiment, reference_date, food_k, restaurant_k, variant="improved"
    )
    delta = {}
    for metric in PRIMARY_METRICS + ("food_precision_at_k", "food_recall_at_k", "food_name_hit_rate_at_k", "restaurant_precision_at_k"):
        before = baseline.get(metric)
        after = improved.get(metric)
        if before is None or after is None:
            delta[metric] = None
        else:
            delta[metric] = float(after) - float(before)
    return {
        "split": "Same leave-last-completed-order-out split. Association rules off in both variants.",
        "baseline": baseline,
        "improved": improved,
        "delta_improved_minus_baseline": delta,
        "prefer_improved": _prefer_improved(delta),
        "decision_note": (
            "Prefer improved only when food hit rate@K rises and restaurant hit rate@K does not fall. "
            "Name-level hit rate is diagnostic and is not used to choose a variant."
        ),
    }


def _prefer_improved(delta: dict[str, object]) -> bool:
    food = delta.get("food_hit_rate_at_k")
    restaurants = delta.get("restaurant_hit_rate_at_k")
    if food is None or restaurants is None:
        return False
    return float(food) > 0 and float(restaurants) >= -1e-12


def _ordered_ids(frame: pd.DataFrame, column: str) -> list[str]:
    if frame is None or frame.empty or column not in frame.columns:
        return []
    ordered = frame.sort_values("rank") if "rank" in frame.columns else frame
    values = []
    for value in ordered[column].map(_token):
        if value:
            values.append(value)
    return values


def _ndcg(recommended: list[str], targets: set[str], k: int) -> float:
    if not targets or k < 1:
        return 0.0
    dcg = 0.0
    for index, item in enumerate(recommended[:k]):
        if item in targets:
            dcg += 1.0 / math.log2(index + 2)
    ideal = min(len(targets), k)
    idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def _name_map(foods: pd.DataFrame) -> dict[str, str]:
    if foods.empty or "name" not in foods.columns:
        return {}
    mapping: dict[str, str] = {}
    for record in foods.loc[:, ["id", "name"]].to_dict("records"):
        item_id = _token(record.get("id"))
        name = record.get("name")
        if item_id and name is not None and not pd.isna(name) and str(name).strip():
            mapping[item_id] = str(name).strip()
    return mapping


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
