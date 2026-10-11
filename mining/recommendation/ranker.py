"""Deterministic recommendation ranking.

The result is a recommendation ranking score. It is not a purchase probability.
Each signal is scaled to the range 0 to 1, then combined with fixed weights.
"""

from __future__ import annotations

import pandas as pd

from mining.recommendation.candidates import food_candidate_rows, restaurant_candidate_rows

FOOD_HISTORY_WEIGHTS = {
    "cuisine_fit": 0.25,
    "association": 0.25,
    "quality": 0.20,
    "familiarity": 0.20,
    "popularity": 0.10,
}
FOOD_COLD_WEIGHTS = {"quality": 0.75, "popularity": 0.25}
RESTAURANT_HISTORY_WEIGHTS = {
    "cuisine_fit": 0.40,
    "quality": 0.40,
    "familiarity": 0.10,
    "popularity": 0.10,
}
RESTAURANT_COLD_WEIGHTS = {"quality": 0.75, "popularity": 0.25}
LIMITED_HISTORY_ORDERS = 2

FOOD_COLUMNS = [
    "customer_id",
    "food_item_id",
    "restaurant_id",
    "recommendation_score",
    "rank",
    "reason",
]
RESTAURANT_COLUMNS = [
    "customer_id",
    "restaurant_id",
    "recommendation_score",
    "rank",
    "reason",
]


def recommend(
    context: dict[str, object],
    rules: pd.DataFrame,
    food_k: int,
    restaurant_k: int,
    limited_history_orders: int = LIMITED_HISTORY_ORDERS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank food and restaurant recommendations for every customer in the context."""
    if food_k < 1 or restaurant_k < 1:
        raise ValueError("food_k and restaurant_k must be integers greater than or equal to 1")
    if limited_history_orders < 1:
        raise ValueError("limited_history_orders must be an integer greater than or equal to 1")
    food_rows: list[dict[str, object]] = []
    restaurant_rows: list[dict[str, object]] = []
    customers: pd.DataFrame = context["customers"]
    rule_rows = _rule_rows(rules)
    lookup: dict[str, dict[str, object]] = context["item_lookup"]
    places: dict[str, dict[str, float]] = context["restaurant_lookup"]
    for customer_id in sorted(customers["customer_id"].dropna().unique(), key=_sort_key):
        profile = _profile(context, str(customer_id))
        food_rows.extend(_rank_food(context, rule_rows, str(customer_id), food_k, limited_history_orders, profile, lookup))
        restaurant_rows.extend(_rank_restaurants(places, str(customer_id), restaurant_k, limited_history_orders, profile, context))
    return _frame(food_rows, FOOD_COLUMNS), _frame(restaurant_rows, RESTAURANT_COLUMNS)


def _rank_food(context, rule_rows, customer_id: str, food_k: int, limited_history_orders: int, profile: dict[str, object], lookup: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    candidates = food_candidate_rows(context, rule_rows, customer_id)
    if not candidates:
        return []
    strengths = _best_strengths(rule_rows, profile["purchased_items"])
    alpha = _alpha(profile["order_count"], limited_history_orders)
    cuisine_share: dict[object, float] = profile["cuisine_share"]
    familiarity: dict[object, float] = profile["familiarity"]
    ranked: list[tuple[float, float, float, int, dict[str, object]]] = []
    for row in candidates:
        item = lookup[str(row["food_item_id"])]
        quality = float(item["quality_score"])
        popularity = float(item["item_popularity"])
        association = strengths.get(str(row["food_item_id"]), 0.0)
        cuisine_fit = float(cuisine_share.get(row["cuisine_type"], 0.0))
        familiar = float(familiarity.get(row["restaurant_id"], 0.0))
        history = (
            FOOD_HISTORY_WEIGHTS["cuisine_fit"] * cuisine_fit
            + FOOD_HISTORY_WEIGHTS["association"] * association
            + FOOD_HISTORY_WEIGHTS["quality"] * quality
            + FOOD_HISTORY_WEIGHTS["familiarity"] * familiar
            + FOOD_HISTORY_WEIGHTS["popularity"] * popularity
        )
        cold = FOOD_COLD_WEIGHTS["quality"] * quality + FOOD_COLD_WEIGHTS["popularity"] * popularity
        score = alpha * history + (1.0 - alpha) * cold
        reason = _food_reason(profile["order_count"], limited_history_orders, str(row["source"]), cuisine_fit, association, quality, bool(row["repeat_item"]))
        ranked.append((score, association, quality, _id_key(row["food_item_id"]), {
            "customer_id": customer_id,
            "food_item_id": row["food_item_id"],
            "restaurant_id": row["restaurant_id"],
            "recommendation_score": score,
            "reason": reason,
        }))
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    kept: list[dict[str, object]] = []
    seen: set[str] = set()
    for score, _association, _quality, _tie, record in ranked:
        item_id = str(record["food_item_id"])
        if item_id in seen:
            continue
        seen.add(item_id)
        record["rank"] = len(kept) + 1
        kept.append(record)
        if len(kept) >= food_k:
            break
    return kept


def _rank_restaurants(places, customer_id: str, restaurant_k: int, limited_history_orders: int, profile: dict[str, object], context: dict[str, object]) -> list[dict[str, object]]:
    candidates = restaurant_candidate_rows(context, customer_id)
    if not candidates:
        return []
    alpha = _alpha(profile["order_count"], limited_history_orders)
    cuisine_share: dict[object, float] = profile["cuisine_share"]
    familiarity: dict[object, float] = profile["familiarity"]
    ranked: list[tuple[float, float, int, dict[str, object]]] = []
    for row in candidates:
        place = places.get(row["restaurant_id"], {})
        quality = float(place.get("quality_score", 0.5))
        popularity = float(place.get("restaurant_popularity", 0.0))
        cuisine_fit = float(cuisine_share.get(row["cuisine_type"], 0.0))
        familiar = float(familiarity.get(row["restaurant_id"], 0.0))
        history = (
            RESTAURANT_HISTORY_WEIGHTS["cuisine_fit"] * cuisine_fit
            + RESTAURANT_HISTORY_WEIGHTS["quality"] * quality
            + RESTAURANT_HISTORY_WEIGHTS["familiarity"] * familiar
            + RESTAURANT_HISTORY_WEIGHTS["popularity"] * popularity
        )
        cold = RESTAURANT_COLD_WEIGHTS["quality"] * quality + RESTAURANT_COLD_WEIGHTS["popularity"] * popularity
        score = alpha * history + (1.0 - alpha) * cold
        reason = _restaurant_reason(profile["order_count"], limited_history_orders, cuisine_fit, quality, familiar, bool(row["repeat_restaurant"]))
        ranked.append((score, quality, _id_key(row["restaurant_id"]), {
            "customer_id": customer_id,
            "restaurant_id": row["restaurant_id"],
            "recommendation_score": score,
            "reason": reason,
        }))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    kept: list[dict[str, object]] = []
    seen: set[str] = set()
    for _score, _quality, _tie, record in ranked:
        restaurant_id = str(record["restaurant_id"])
        if restaurant_id in seen:
            continue
        seen.add(restaurant_id)
        record["rank"] = len(kept) + 1
        kept.append(record)
        if len(kept) >= restaurant_k:
            break
    return kept


def _rule_rows(rules: pd.DataFrame) -> list[tuple[str, str, float]]:
    if rules.empty:
        return []
    return list(zip(rules["antecedent_id"].astype(str), rules["consequent_id"].astype(str), rules["association_strength"].astype(float)))


def _profile(context: dict[str, object], customer_id: str) -> dict[str, object]:
    purchases: pd.DataFrame = context["purchases"]
    grouped = context.get("purchases_by_customer")
    if isinstance(grouped, dict):
        mine = grouped.get(customer_id, purchases.iloc[0:0])
    else:
        mine = purchases.loc[purchases["customer_id"] == customer_id]
    orders = mine.drop_duplicates("order_id")
    order_count = int(len(orders))
    cuisine_share = {}
    familiarity = {}
    if order_count:
        cuisine_share = (orders.groupby("cuisine_type").size() / order_count).to_dict()
        restaurant_share = orders.groupby("restaurant_id").size() / order_count
        last = orders.groupby("restaurant_id")["order_timestamp"].max()
        cutoff = context["cutoff"]
        for restaurant_id, share in restaurant_share.items():
            days = max((cutoff - last.at[restaurant_id]).days, 0)
            recency = 1.0 / (1.0 + days / 30.0)
            familiarity[restaurant_id] = 0.5 * float(share) + 0.5 * recency
    return {
        "order_count": order_count,
        "cuisine_share": cuisine_share,
        "familiarity": familiarity,
        "purchased_items": set(mine["food_item_id"]),
    }


def _best_strengths(rule_rows: list[tuple[str, str, float]], purchased: set[str]) -> dict[str, float]:
    if not rule_rows or not purchased:
        return {}
    owned = {str(item) for item in purchased}
    best: dict[str, float] = {}
    for antecedent, consequent, strength in rule_rows:
        if antecedent not in owned:
            continue
        current = best.get(consequent)
        if current is None or strength > current:
            best[consequent] = strength
    return best


def _food_reason(order_count: int, limited_history_orders: int, source: str, cuisine_fit: float, association_strength: float, quality_score: float, repeat_item: bool) -> str:
    if order_count == 0 or (order_count <= limited_history_orders and source == "cold_start" and cuisine_fit == 0 and association_strength == 0):
        return "general pick for limited history"
    contributions = {
        "associated with a previously purchased item": FOOD_HISTORY_WEIGHTS["association"] * association_strength,
        "frequently purchased cuisine": FOOD_HISTORY_WEIGHTS["cuisine_fit"] * cuisine_fit,
        "highly rated in preferred cuisine": FOOD_HISTORY_WEIGHTS["quality"] * quality_score if cuisine_fit > 0 else 0.0,
        "previously reordered item": 0.05 if repeat_item else 0.0,
    }
    best = max(contributions, key=contributions.get)
    if contributions[best] <= 0:
        return "general pick for limited history"
    return best


def _restaurant_reason(order_count: int, limited_history_orders: int, cuisine_fit: float, quality_score: float, familiarity: float, repeat_restaurant: bool) -> str:
    if order_count == 0:
        return "general pick for limited history"
    if repeat_restaurant and familiarity >= cuisine_fit:
        return "previously highly rated restaurant"
    if cuisine_fit > 0 and quality_score >= cuisine_fit:
        return "highly rated in preferred cuisine"
    if cuisine_fit > 0:
        return "frequently purchased cuisine"
    if order_count <= limited_history_orders:
        return "general pick for limited history"
    return "highly rated restaurant"


def _alpha(order_count: int, limited_history_orders: int) -> float:
    if order_count <= 0:
        return 0.0
    return min(1.0, order_count / (limited_history_orders + 1))


def _frame(rows: list[dict[str, object]], columns: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def _id_key(value: object) -> int:
    try:
        return int(str(value))
    except ValueError:
        return 10**18


def _sort_key(value: str) -> tuple[int, str]:
    try:
        return (int(value), value)
    except ValueError:
        return (10**18, value)
