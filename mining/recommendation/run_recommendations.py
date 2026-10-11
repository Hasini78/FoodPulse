"""Rank offline food and restaurant recommendations.

From the repository root:

    python -m mining.recommendation.run_recommendations --reference-date 2026-10-11

The command reads processed Parquet files and writes new recommendation outputs.
It does not modify the source files or connect to a database.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mining.recommendation.candidates import build_context, load_association_rules, parse_cutoff
from mining.recommendation.evaluate import evaluate_holdout
from mining.recommendation.ranker import (
    FOOD_COLD_WEIGHTS,
    FOOD_HISTORY_WEIGHTS,
    LIMITED_HISTORY_ORDERS,
    RESTAURANT_COLD_WEIGHTS,
    RESTAURANT_HISTORY_WEIGHTS,
    recommend,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
ARTIFACTS = PROJECT_ROOT / "mining" / "recommendation" / "artifacts"


def run_recommendations(
    customers_path: Path,
    orders_path: Path,
    order_items_path: Path,
    foods_path: Path,
    restaurants_path: Path,
    reviews_path: Path,
    sentiment_path: Path,
    rules_path: Path,
    output_dir: Path,
    artifacts_dir: Path,
    reference_date: str,
    food_k: int,
    restaurant_k: int,
    limited_history_orders: int,
) -> dict[str, object]:
    """Build recommendations, evaluate a temporal holdout, and write artifacts."""
    for path in (customers_path, orders_path, order_items_path, foods_path, restaurants_path, reviews_path, sentiment_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
    if food_k < 1 or restaurant_k < 1 or limited_history_orders < 1:
        raise ValueError("food_k, restaurant_k, and limited_history_orders must be integers greater than or equal to 1")
    parsed = parse_cutoff(reference_date)
    customers = pd.read_parquet(customers_path)
    orders = pd.read_parquet(orders_path)
    order_items = pd.read_parquet(order_items_path)
    foods = pd.read_parquet(foods_path)
    restaurants = pd.read_parquet(restaurants_path)
    reviews = pd.read_parquet(reviews_path)
    sentiment = pd.read_parquet(sentiment_path)
    rules, rule_warnings = load_association_rules(rules_path, foods)
    context = build_context(customers, orders, order_items, foods, restaurants, reviews, sentiment, parsed)
    food, restaurant = recommend(context, rules, food_k, restaurant_k, limited_history_orders)
    evaluation = evaluate_holdout(
        customers, orders, order_items, foods, restaurants, reviews, sentiment, parsed, food_k, restaurant_k
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    food_path = output_dir / "food_recommendations.parquet"
    restaurant_path = output_dir / "restaurant_recommendations.parquet"
    metrics_path = output_dir / "recommendation_metrics.json"
    chart_path = artifacts_dir / "recommendation_reasons.png"
    food.to_parquet(food_path, index=False)
    restaurant.to_parquet(restaurant_path, index=False)
    if food.empty and restaurant.empty:
        chart_written = False
    else:
        _plot(food, restaurant, chart_path)
        chart_written = True
    customers_with_food = int(food["customer_id"].nunique()) if not food.empty else 0
    customers_with_restaurants = int(restaurant["customer_id"].nunique()) if not restaurant.empty else 0
    customer_count = int(context["customers"]["customer_id"].nunique())
    payload: dict[str, object] = {
        "inputs": {
            "customers": str(customers_path),
            "orders": str(orders_path),
            "order_items": str(order_items_path),
            "food_items": str(foods_path),
            "restaurants": str(restaurants_path),
            "reviews": str(reviews_path),
            "review_sentiment": str(sentiment_path),
            "association_rules": str(rules_path),
        },
        "reference_date": parsed.isoformat(),
        "counts": {
            "customers": customer_count,
            "customers_with_food_recommendations": customers_with_food,
            "customers_with_restaurant_recommendations": customers_with_restaurants,
            "food_recommendations": int(len(food)),
            "restaurant_recommendations": int(len(restaurant)),
            "usable_association_rules": int(len(rules)),
            "customers_without_food_recommendations": customer_count - customers_with_food,
            "customers_without_restaurant_recommendations": customer_count - customers_with_restaurants,
        },
        "config": {
            "food_k": food_k,
            "restaurant_k": restaurant_k,
            "limited_history_orders": limited_history_orders,
            "food_history_weights": FOOD_HISTORY_WEIGHTS,
            "food_cold_weights": FOOD_COLD_WEIGHTS,
            "restaurant_history_weights": RESTAURANT_HISTORY_WEIGHTS,
            "restaurant_cold_weights": RESTAURANT_COLD_WEIGHTS,
            "blend": "Customers with no completed orders use the cold-start weights. Others use min(1, completed_orders / (limited_history_orders + 1)) times the history score plus the rest from the cold-start score.",
            "purchased_items": "An item bought once is not recommended. An item bought on two or more completed orders can be recommended as a reorder.",
            "tie_break": "Higher score, then higher association strength or quality, then lower id.",
            "score_name": "recommendation ranking score",
        },
        "warnings": [*rule_warnings, *context["warnings"]],
        "evaluation": evaluation,
        "empty_result": food.empty and restaurant.empty,
        "limitations": [
            "The score ranks candidates. It is not a probability of purchase and does not measure satisfaction or sales.",
            "Association describes co-purchase, not a cause.",
            "Global association rules can include the same orders used as a future holdout, so the holdout turns that signal off.",
            "Popularity is a small weight and is not used as the explanation when another signal is present.",
            "Names, emails, and phone numbers are not recommendation fields.",
        ],
        "artifacts": {
            "food": str(food_path),
            "restaurants": str(restaurant_path),
            "metrics": str(metrics_path),
            "reason_chart": str(chart_path) if chart_written else None,
        },
    }
    if food.empty and restaurant.empty:
        payload["empty_result_reason"] = "No eligible food items or restaurants were available for the supplied customers."
    metrics_path.write_text(json.dumps(_json_ready(payload), indent=2), encoding="utf-8")
    logger.info("Wrote %s food and %s restaurant recommendations", len(food), len(restaurant))
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Rank food and restaurant recommendations from completed orders, reviews, and association rules.")
    parser.add_argument("--customers", type=Path, default=PROCESSED / "customer_features.parquet")
    parser.add_argument("--orders", type=Path, default=PROCESSED / "orders.parquet")
    parser.add_argument("--order-items", type=Path, default=PROCESSED / "order_items.parquet")
    parser.add_argument("--food-items", type=Path, default=PROCESSED / "food_items.parquet")
    parser.add_argument("--restaurants", type=Path, default=PROCESSED / "restaurants.parquet")
    parser.add_argument("--reviews", type=Path, default=PROCESSED / "reviews.parquet")
    parser.add_argument("--sentiment", type=Path, default=PROCESSED / "review_sentiment.parquet")
    parser.add_argument("--rules", type=Path, default=PROCESSED / "association_rules.parquet")
    parser.add_argument("--output-dir", type=Path, default=PROCESSED)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS)
    parser.add_argument("--reference-date", default="2026-10-11")
    parser.add_argument("--food-k", type=int, default=5)
    parser.add_argument("--restaurant-k", type=int, default=3)
    parser.add_argument("--limited-history-orders", type=int, default=LIMITED_HISTORY_ORDERS)
    args = parser.parse_args(argv)
    try:
        run_recommendations(
            args.customers,
            args.orders,
            args.order_items,
            args.food_items,
            args.restaurants,
            args.reviews,
            args.sentiment,
            args.rules,
            args.output_dir,
            args.artifacts_dir,
            args.reference_date,
            args.food_k,
            args.restaurant_k,
            args.limited_history_orders,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _plot(food: pd.DataFrame, restaurants: pd.DataFrame, path: Path) -> None:
    reasons = []
    if not food.empty:
        reasons.append(food["reason"])
    if not restaurants.empty:
        reasons.append(restaurants["reason"])
    counts = pd.concat(reasons).value_counts().sort_index()
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.bar(counts.index, counts.values)
    axis.set_ylabel("Recommendations")
    axis.set_title("Recommendation reasons")
    axis.tick_params(axis="x", rotation=30)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    logger.info("Wrote reason chart to %s", path)


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, str):
        return value
    if pd.isna(value):
        return None
    return value


if __name__ == "__main__":
    sys.exit(main())
