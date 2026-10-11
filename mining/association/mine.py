"""Frequent itemsets and association rules from order baskets.

Apriori (mlxtend) finds the itemsets. Rules use mlxtend's support,
confidence, lift, leverage, and conviction. These describe co-occurrence
in completed orders. They do not show that one item causes another.
"""

from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

from mining.association.baskets import BasketBuild

ITEMSET_COLUMNS = [
    "item_ids",
    "item_names",
    "itemset_size",
    "support_count",
    "support",
    "restaurant_scope",
]
RULE_COLUMNS = [
    "antecedent_ids",
    "antecedent_names",
    "consequent_ids",
    "consequent_names",
    "support_count",
    "support",
    "confidence",
    "lift",
    "leverage",
    "conviction",
    "restaurant_scope",
]

METRIC_DEFINITIONS = {
    "support": "support(X) = (transactions containing every item in X) / (transactions in this scope).",
    "confidence": "confidence(A -> C) = support(A union C) / support(A).",
    "lift": "lift(A -> C) = confidence(A -> C) / support(C). Lift near 1 means A and C co-occur about as often as chance.",
    "leverage": "leverage(A -> C) = support(A union C) - support(A) * support(C).",
    "conviction": (
        "conviction(A -> C) = (1 - support(C)) / (1 - confidence(A -> C)). "
        "The value is null when confidence is 1 or the denominator is otherwise zero."
    ),
    "association_is_not_causation": (
        "A rule only says the items were bought in the same completed orders. "
        "It does not say that the antecedent caused the consequent."
    ),
}


def validate_thresholds(
    min_support: float,
    min_confidence: float,
    min_lift: float | None,
    min_restaurant_transactions: int,
) -> None:
    """Reject thresholds that are not usable fractions or counts."""
    _unit_fraction("min_support", min_support)
    _unit_fraction("min_confidence", min_confidence)
    if min_lift is not None:
        if isinstance(min_lift, bool) or not isinstance(min_lift, (int, float)):
            raise ValueError("min_lift must be a number greater than or equal to 0")
        if not math.isfinite(float(min_lift)) or float(min_lift) < 0:
            raise ValueError("min_lift must be a finite number greater than or equal to 0")
    if (
        isinstance(min_restaurant_transactions, bool)
        or not isinstance(min_restaurant_transactions, int)
        or min_restaurant_transactions < 1
    ):
        raise ValueError("min_restaurant_transactions must be an integer greater than or equal to 1")


def mine_baskets(
    built: BasketBuild,
    min_support: float,
    min_confidence: float,
    min_lift: float | None,
    restaurant_specific: bool,
    min_restaurant_transactions: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Mine one global scope, or each restaurant separately."""
    validate_thresholds(min_support, min_confidence, min_lift, min_restaurant_transactions)
    if restaurant_specific:
        itemsets, rules, scope_stats = _mine_by_restaurant(
            built,
            min_support,
            min_confidence,
            min_lift,
            min_restaurant_transactions,
        )
    else:
        itemsets, rules = _mine_scope(
            built.transactions,
            built.item_names,
            min_support,
            min_confidence,
            min_lift,
            "all",
        )
        scope_stats = {
            "mode": "all_completed_orders",
            "restaurants_processed": sorted(set(built.restaurant_ids), key=_sort_token),
            "restaurants_skipped": [],
            "skipped_reason": None,
        }
    summary = {
        "algorithm": "apriori",
        "library": "mlxtend",
        "fp_growth": (
            "Not used. Apriori on these basket counts finishes directly and is the requested algorithm."
        ),
        "thresholds": {
            "min_support": min_support,
            "min_confidence": min_confidence,
            "min_lift": min_lift,
            "min_restaurant_transactions": min_restaurant_transactions,
        },
        "itemset_count": int(len(itemsets)),
        "rule_count": int(len(rules)),
        "itemset_size_counts": _size_counts(itemsets),
        "scope": scope_stats,
        "metric_definitions": METRIC_DEFINITIONS,
    }
    return itemsets, rules, summary


def _mine_by_restaurant(
    built: BasketBuild,
    min_support: float,
    min_confidence: float,
    min_lift: float | None,
    min_restaurant_transactions: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    grouped: dict[str, list[list[str]]] = defaultdict(list)
    for restaurant_id, basket in zip(built.restaurant_ids, built.transactions):
        grouped[restaurant_id].append(basket)
    itemset_frames: list[pd.DataFrame] = []
    rule_frames: list[pd.DataFrame] = []
    processed: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for restaurant_id in sorted(grouped, key=_sort_token):
        baskets = grouped[restaurant_id]
        if len(baskets) < min_restaurant_transactions:
            skipped.append(
                {
                    "restaurant_id": restaurant_id,
                    "valid_transactions": len(baskets),
                    "reason": (
                        f"fewer than {min_restaurant_transactions} valid transactions"
                    ),
                }
            )
            continue
        names = {
            item_id: built.item_names[item_id]
            for basket in baskets
            for item_id in basket
        }
        itemsets, rules = _mine_scope(
            baskets,
            names,
            min_support,
            min_confidence,
            min_lift,
            restaurant_id,
        )
        itemset_frames.append(itemsets)
        rule_frames.append(rules)
        processed.append(
            {
                "restaurant_id": restaurant_id,
                "valid_transactions": len(baskets),
                "distinct_items": len(names),
                "itemset_count": int(len(itemsets)),
                "rule_count": int(len(rules)),
            }
        )
    return (
        _concat(itemset_frames, ITEMSET_COLUMNS),
        _concat(rule_frames, RULE_COLUMNS),
        {
            "mode": "restaurant_specific",
            "restaurants_processed": processed,
            "restaurants_skipped": skipped,
            "skipped_reason": (
                "A restaurant is skipped when its own valid completed orders "
                "are below min_restaurant_transactions. Its baskets are not merged "
                "with any other restaurant."
            ),
        },
    )


def _mine_scope(
    transactions: list[list[str]],
    item_names: dict[str, str],
    min_support: float,
    min_confidence: float,
    min_lift: float | None,
    scope: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    transaction_count = len(transactions)
    if transaction_count == 0:
        return _empty_itemsets(), _empty_rules()
    minimum_count = math.ceil(min_support * transaction_count - 1e-9)
    if minimum_count > transaction_count:
        return _empty_itemsets(), _empty_rules()
    encoder = TransactionEncoder()
    encoded = encoder.fit(transactions).transform(transactions)
    matrix = pd.DataFrame(encoded, columns=encoder.columns_)
    frequent = apriori(
        matrix,
        min_support=minimum_count / transaction_count,
        use_colnames=True,
    )
    if frequent.empty:
        return _empty_itemsets(), _empty_rules()
    itemsets = _format_itemsets(frequent, transaction_count, item_names, scope)
    itemsets = itemsets.loc[itemsets["support_count"] >= minimum_count].reset_index(drop=True)
    if itemsets.empty or int(itemsets["itemset_size"].max()) < 2:
        return itemsets, _empty_rules()
    raw_rules = association_rules(
        frequent,
        metric="confidence",
        min_threshold=min_confidence,
        num_itemsets=transaction_count,
        return_metrics=[
            "antecedent support",
            "consequent support",
            "support",
            "confidence",
            "lift",
            "leverage",
            "conviction",
        ],
    )
    rules = _format_rules(raw_rules, transaction_count, item_names, scope, min_lift)
    return itemsets, rules


def _format_itemsets(
    frequent: pd.DataFrame,
    transaction_count: int,
    item_names: dict[str, str],
    scope: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for itemset, support in zip(frequent["itemsets"], frequent["support"]):
        ids = _sorted_ids(itemset)
        if not ids:
            continue
        count = int(round(float(support) * transaction_count))
        rows.append(
            {
                "item_ids": ",".join(ids),
                "item_names": " | ".join(item_names.get(item_id, "") for item_id in ids),
                "itemset_size": len(ids),
                "support_count": count,
                "support": count / transaction_count,
                "restaurant_scope": scope,
            }
        )
    frame = pd.DataFrame(rows, columns=ITEMSET_COLUMNS)
    return _sort_itemsets(frame)


def _format_rules(
    raw_rules: pd.DataFrame,
    transaction_count: int,
    item_names: dict[str, str],
    scope: str,
    min_lift: float | None,
) -> pd.DataFrame:
    if raw_rules.empty:
        return _empty_rules()
    rows: list[dict[str, object]] = []
    for rule in raw_rules.itertuples(index=False):
        antecedent = _sorted_ids(rule.antecedents)
        consequent = _sorted_ids(rule.consequents)
        if not antecedent or not consequent:
            continue
        support = float(rule.support)
        count = int(round(support * transaction_count))
        confidence = float(rule.confidence)
        lift = float(rule.lift)
        leverage = float(rule.leverage)
        conviction = float(rule.conviction)
        if min_lift is not None and (not math.isfinite(lift) or lift < min_lift):
            continue
        rows.append(
            {
                "antecedent_ids": ",".join(antecedent),
                "antecedent_names": " | ".join(item_names.get(item_id, "") for item_id in antecedent),
                "consequent_ids": ",".join(consequent),
                "consequent_names": " | ".join(item_names.get(item_id, "") for item_id in consequent),
                "support_count": count,
                "support": count / transaction_count,
                "confidence": confidence,
                "lift": None if not math.isfinite(lift) else lift,
                "leverage": None if not math.isfinite(leverage) else leverage,
                "conviction": None if not math.isfinite(conviction) else conviction,
                "restaurant_scope": scope,
            }
        )
    frame = pd.DataFrame(rows, columns=RULE_COLUMNS)
    if frame.empty:
        return _empty_rules()
    return frame.sort_values(
        by=["lift", "confidence", "support", "antecedent_ids", "consequent_ids"],
        ascending=[False, False, False, True, True],
        na_position="last",
    ).reset_index(drop=True)


def _sorted_ids(values: object) -> list[str]:
    return sorted((str(value) for value in values), key=lambda item: (_sort_token(item), item))


def _sort_itemsets(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty_itemsets()
    return frame.sort_values(
        by=["itemset_size", "support", "item_ids"],
        ascending=[True, False, True],
    ).reset_index(drop=True)


def _empty_itemsets() -> pd.DataFrame:
    return pd.DataFrame(columns=ITEMSET_COLUMNS)


def _empty_rules() -> pd.DataFrame:
    return pd.DataFrame(columns=RULE_COLUMNS)


def _concat(frames: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)


def _size_counts(itemsets: pd.DataFrame) -> dict[str, int]:
    if itemsets.empty:
        return {}
    counts = itemsets["itemset_size"].value_counts().sort_index()
    return {str(int(size)): int(count) for size, count in counts.items()}


def _unit_fraction(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a fraction greater than 0 and at most 1")
    if not math.isfinite(float(value)) or float(value) <= 0 or float(value) > 1:
        raise ValueError(f"{name} must be a fraction greater than 0 and at most 1")


def _sort_token(value: str) -> tuple[int, str]:
    try:
        return (int(value), value)
    except ValueError:
        return (10**18, value)
