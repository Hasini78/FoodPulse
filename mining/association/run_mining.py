"""Run association-rule mining on completed FoodPulse orders.

From the repository root:

    python -m mining.association.run_mining
    python -m mining.association.run_mining --min-support 0.003 --min-confidence 0.3
    python -m mining.association.run_mining --restaurant-specific --min-support 0.05

The command reads processed Parquet files and writes new association outputs.
It does not modify the source files or connect to a database.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from mining.association.baskets import build_baskets
from mining.association.mine import mine_baskets

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"

DEFAULT_MIN_SUPPORT = 0.003
DEFAULT_MIN_CONFIDENCE = 0.3
DEFAULT_MIN_RESTAURANT_TRANSACTIONS = 30


def run_mining(
    orders_path: Path,
    order_items_path: Path,
    food_items_path: Path,
    output_dir: Path,
    min_support: float,
    min_confidence: float,
    min_lift: float | None,
    restaurant_specific: bool,
    min_restaurant_transactions: int,
) -> dict[str, object]:
    """Read baskets, mine rules, and write the three association artifacts."""
    for path in (orders_path, order_items_path, food_items_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
    orders = pd.read_parquet(orders_path)
    order_items = pd.read_parquet(order_items_path)
    food_items = pd.read_parquet(food_items_path)
    built = build_baskets(orders, order_items, food_items)
    itemsets, rules, summary = mine_baskets(
        built,
        min_support,
        min_confidence,
        min_lift,
        restaurant_specific,
        min_restaurant_transactions,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    itemset_path = output_dir / "association_frequent_itemsets.parquet"
    rule_path = output_dir / "association_rules.parquet"
    metrics_path = output_dir / "association_mining_metrics.json"
    itemsets.to_parquet(itemset_path, index=False)
    rules.to_parquet(rule_path, index=False)
    payload: dict[str, object] = {
        "inputs": {
            "orders": str(orders_path),
            "order_items": str(order_items_path),
            "food_items": str(food_items_path),
        },
        "filters": {
            "order_status": "completed, compared after trimming and lowercasing",
            "excluded_statuses": ["cancelled", "pending", "any other non-completed status"],
            "basket": (
                "One basket per completed (restaurant_id, order_id). "
                "Distinct food-item ids only. Quantity is not support."
            ),
            "identity": "Food-item ids are the items. Names are labels and are not merged.",
            "privacy": "Customer ids, phones, emails, and other personal fields are not mining inputs.",
            "restaurant_isolation": (
                "An item is kept only when its food-item restaurant matches the order restaurant. "
                "Restaurant-specific mode mines each restaurant on its own baskets."
            ),
        },
        "transactions": built.stats,
        **summary,
        "empty_result": int(len(itemsets)) == 0,
        "limitations": [
            "Each food item belongs to one restaurant, so the same dish name at two restaurants is two items.",
            "Global support uses every completed order as the denominator, which dilutes pairs that exist at only one restaurant.",
            "Rules describe co-purchase, not a causal menu effect.",
            "Conviction is null when it would be infinite or undefined.",
            "No itemset size cap is applied. A high minimum support can still leave only size-1 itemsets and no rules.",
        ],
        "artifacts": {
            "frequent_itemsets": str(itemset_path),
            "rules": str(rule_path),
            "metrics": str(metrics_path),
        },
    }
    if int(len(itemsets)) == 0:
        payload["empty_result_reason"] = (
            "No itemset met min_support in the selected scope. "
            "The output files keep the column schema and contain no rows."
        )
    elif int(len(rules)) == 0:
        payload["empty_result_reason"] = (
            "Frequent itemsets were found, but none produced a rule at the requested "
            "confidence and lift thresholds."
        )
    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(
        "Wrote %s itemsets and %s rules from %s transactions",
        len(itemsets),
        len(rules),
        built.stats["valid_transactions"],
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Find food items bought together in completed orders. "
            "Support is the share of baskets containing an itemset. "
            "Confidence, lift, leverage, and conviction score rules. "
            "Association is not causation."
        )
    )
    parser.add_argument("--orders", type=Path, default=PROCESSED / "orders.parquet")
    parser.add_argument("--order-items", type=Path, default=PROCESSED / "order_items.parquet")
    parser.add_argument("--food-items", type=Path, default=PROCESSED / "food_items.parquet")
    parser.add_argument("--output-dir", type=Path, default=PROCESSED)
    parser.add_argument(
        "--min-support",
        type=float,
        default=DEFAULT_MIN_SUPPORT,
        help=(
            "Minimum support as a fraction of transactions in the scope being mined. "
            f"Default {DEFAULT_MIN_SUPPORT}, about 14 of 4405 global completed orders."
        ),
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help=f"Minimum confidence for a rule. Default {DEFAULT_MIN_CONFIDENCE}.",
    )
    parser.add_argument(
        "--min-lift",
        type=float,
        default=None,
        help="Optional minimum lift. Omit it to keep every rule that passes confidence.",
    )
    parser.add_argument(
        "--restaurant-specific",
        action="store_true",
        help="Mine each restaurant's baskets separately. Never pools restaurants together.",
    )
    parser.add_argument(
        "--min-restaurant-transactions",
        type=int,
        default=DEFAULT_MIN_RESTAURANT_TRANSACTIONS,
        help=(
            "In restaurant-specific mode, skip a restaurant with fewer valid transactions. "
            f"Default {DEFAULT_MIN_RESTAURANT_TRANSACTIONS}."
        ),
    )
    args = parser.parse_args(argv)
    try:
        run_mining(
            args.orders,
            args.order_items,
            args.food_items,
            args.output_dir,
            args.min_support,
            args.min_confidence,
            args.min_lift,
            args.restaurant_specific,
            args.min_restaurant_transactions,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
