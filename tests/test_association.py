"""Tests for completed-order baskets and association rules."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from mining.association.baskets import build_baskets
from mining.association.mine import mine_baskets, validate_thresholds
from mining.association.run_mining import main, run_mining


def _orders(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _items(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _foods(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _known_world() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    orders = _orders(
        [
            {"id": 1, "restaurant_id": 10, "status": "completed", "customer_id": 900, "customer_email": "a@example.com"},
            {"id": 2, "restaurant_id": 10, "status": "Completed", "customer_id": 901},
            {"id": 3, "restaurant_id": 10, "status": "completed", "customer_id": 902},
            {"id": 4, "restaurant_id": 10, "status": "completed", "customer_id": 903},
        ]
    )
    items = _items(
        [
            {"order_id": 1, "food_item_id": 1, "quantity": 2},
            {"order_id": 1, "food_item_id": 2, "quantity": 1},
            {"order_id": 2, "food_item_id": 1, "quantity": 1},
            {"order_id": 2, "food_item_id": 2, "quantity": 1},
            {"order_id": 3, "food_item_id": 1, "quantity": 4},
            {"order_id": 3, "food_item_id": 3, "quantity": 1},
            {"order_id": 4, "food_item_id": 2, "quantity": 1},
            {"order_id": 4, "food_item_id": 3, "quantity": 1},
        ]
    )
    foods = _foods(
        [
            {"id": 1, "restaurant_id": 10, "name": "Milk"},
            {"id": 2, "restaurant_id": 10, "name": "Bread"},
            {"id": 3, "restaurant_id": 10, "name": "Butter"},
        ]
    )
    return orders, items, foods


def test_known_baskets_ignore_quantity_and_customer_fields() -> None:
    orders, items, foods = _known_world()
    built = build_baskets(orders, items, foods)
    assert built.transactions == [["1", "2"], ["1", "2"], ["1", "3"], ["2", "3"]]
    assert built.stats["source_orders"] == 4
    assert built.stats["eligible_completed_orders"] == 4
    assert built.stats["valid_transactions"] == 4
    assert built.stats["distinct_items"] == 3
    assert "customer_id" not in json.dumps(built.stats)


def test_completed_orders_and_invalid_records_are_excluded() -> None:
    orders = _orders(
        [
            {"id": 1, "restaurant_id": 10, "status": "completed"},
            {"id": 2, "restaurant_id": 10, "status": "cancelled"},
            {"id": 3, "restaurant_id": 10, "status": "pending"},
            {"id": 4, "restaurant_id": 10, "status": "completed"},
            {"id": None, "restaurant_id": 10, "status": "completed"},
            {"id": 5, "restaurant_id": None, "status": "completed"},
            {"id": 1, "restaurant_id": 10, "status": "completed"},
        ]
    )
    items = _items(
        [
            {"order_id": 1, "food_item_id": 1, "quantity": 1},
            {"order_id": 1, "food_item_id": 1, "quantity": 3},
            {"order_id": 1, "food_item_id": 2, "quantity": 0},
            {"order_id": 1, "food_item_id": 99, "quantity": 1},
            {"order_id": 1, "food_item_id": 4, "quantity": 1},
            {"order_id": 2, "food_item_id": 1, "quantity": 1},
            {"order_id": 3, "food_item_id": 1, "quantity": 1},
            {"order_id": None, "food_item_id": 1, "quantity": 1},
            {"order_id": 1, "food_item_id": None, "quantity": 1},
            {"order_id": 404, "food_item_id": 1, "quantity": 1},
            {"order_id": 4, "food_item_id": 3, "quantity": 1},
        ]
    )
    foods = _foods(
        [
            {"id": 1, "restaurant_id": 10, "name": "Milk"},
            {"id": 2, "restaurant_id": 10, "name": "Bread"},
            {"id": 3, "restaurant_id": 11, "name": "Soup"},
            {"id": 4, "restaurant_id": 11, "name": "Nachos"},
            {"id": 5, "restaurant_id": 10, "name": "  "},
        ]
    )
    built = build_baskets(orders, items, foods)
    assert built.transactions == [["1"]]
    excluded = built.stats["excluded_records"]
    assert excluded["orders_missing_id"] == 1
    assert excluded["orders_missing_restaurant_id"] == 1
    assert excluded["duplicate_order_keys"] == 1
    assert excluded["orders_not_completed"] == 2
    assert excluded["duplicate_items_within_order"] == 1
    assert excluded["order_items_invalid_quantity"] == 1
    assert excluded["order_items_unknown_food"] == 1
    assert excluded["order_items_restaurant_mismatch"] == 2
    assert excluded["order_items_not_on_completed_order"] == 2
    assert excluded["order_items_missing_order_id"] == 1
    assert excluded["order_items_missing_food_item_id"] == 1
    assert excluded["order_items_unknown_order"] == 1
    assert excluded["completed_orders_without_valid_items"] == 1
    assert built.stats["eligible_completed_orders"] == 2
    assert built.stats["valid_transactions"] == 1


def test_same_order_id_at_two_restaurants_stays_separate() -> None:
    orders = _orders(
        [
            {"id": 7, "restaurant_id": 1, "status": "completed"},
            {"id": 7, "restaurant_id": 2, "status": "completed"},
        ]
    )
    items = _items(
        [
            {"order_id": 7, "food_item_id": 10, "quantity": 1},
            {"order_id": 7, "food_item_id": 20, "quantity": 1},
        ]
    )
    foods = _foods(
        [
            {"id": 10, "restaurant_id": 1, "name": "Nachos"},
            {"id": 20, "restaurant_id": 2, "name": "Nachos"},
        ]
    )
    built = build_baskets(orders, items, foods)
    assert list(zip(built.restaurant_ids, built.transactions)) == [
        ("1", ["10"]),
        ("2", ["20"]),
    ]
    assert built.item_names["10"] == "Nachos"
    assert built.item_names["20"] == "Nachos"


def test_known_support_confidence_lift_leverage_and_undefined_conviction() -> None:
    orders, items, foods = _known_world()
    built = build_baskets(orders, items, foods)
    itemsets, rules, _summary = mine_baskets(
        built,
        min_support=0.5,
        min_confidence=0.6,
        min_lift=None,
        restaurant_specific=False,
        min_restaurant_transactions=1,
    )
    pairs = itemsets.loc[itemsets["itemset_size"] == 2]
    assert pairs["item_ids"].tolist() == ["1,2"]
    assert int(pairs["support_count"].iloc[0]) == 2
    assert pairs["support"].iloc[0] == pytest.approx(0.5)
    singles = itemsets.loc[itemsets["itemset_size"] == 1].set_index("item_ids")
    assert int(singles.loc["1", "support_count"]) == 3
    assert int(singles.loc["3", "support_count"]) == 2
    assert rules["antecedent_ids"].tolist() == ["1", "2"]
    assert rules["consequent_ids"].tolist() == ["2", "1"]
    assert rules["confidence"].iloc[0] == pytest.approx(2 / 3)
    assert rules["lift"].iloc[0] == pytest.approx(0.5 / (0.75 * 0.75))
    assert rules["leverage"].iloc[0] == pytest.approx(0.5 - 0.75 * 0.75)
    assert rules["conviction"].iloc[0] == pytest.approx(0.75)

    certain_orders = _orders(
        [
            {"id": 1, "restaurant_id": 1, "status": "completed"},
            {"id": 2, "restaurant_id": 1, "status": "completed"},
        ]
    )
    certain_items = _items(
        [
            {"order_id": 1, "food_item_id": 1, "quantity": 1},
            {"order_id": 1, "food_item_id": 2, "quantity": 1},
            {"order_id": 2, "food_item_id": 1, "quantity": 1},
            {"order_id": 2, "food_item_id": 2, "quantity": 1},
        ]
    )
    certain = build_baskets(certain_orders, certain_items, foods.iloc[:2])
    _itemsets, certain_rules, _summary = mine_baskets(
        certain,
        min_support=1,
        min_confidence=1,
        min_lift=None,
        restaurant_specific=False,
        min_restaurant_transactions=1,
    )
    assert certain_rules["confidence"].eq(1).all()
    assert certain_rules["conviction"].isna().all()


def test_multi_item_rule_and_lift_filter() -> None:
    orders = _orders(
        [
            {"id": index, "restaurant_id": 1, "status": "completed"}
            for index in range(1, 5)
        ]
    )
    items = _items(
        [
            {"order_id": 1, "food_item_id": 1, "quantity": 1},
            {"order_id": 1, "food_item_id": 2, "quantity": 1},
            {"order_id": 1, "food_item_id": 3, "quantity": 1},
            {"order_id": 2, "food_item_id": 1, "quantity": 1},
            {"order_id": 2, "food_item_id": 2, "quantity": 1},
            {"order_id": 2, "food_item_id": 3, "quantity": 1},
            {"order_id": 3, "food_item_id": 1, "quantity": 1},
            {"order_id": 4, "food_item_id": 4, "quantity": 1},
        ]
    )
    foods = _foods(
        [
            {"id": 1, "restaurant_id": 1, "name": "A"},
            {"id": 2, "restaurant_id": 1, "name": "B"},
            {"id": 3, "restaurant_id": 1, "name": "C"},
            {"id": 4, "restaurant_id": 1, "name": "D"},
        ]
    )
    built = build_baskets(orders, items, foods)
    itemsets, rules, _summary = mine_baskets(
        built,
        min_support=0.5,
        min_confidence=0.5,
        min_lift=None,
        restaurant_specific=False,
        min_restaurant_transactions=1,
    )
    assert "1,2,3" in set(itemsets["item_ids"])
    multi = rules.loc[rules["antecedent_ids"] == "1,2"]
    assert multi["consequent_ids"].iloc[0] == "3"
    assert multi["confidence"].iloc[0] == pytest.approx(1)
    assert multi["conviction"].isna().all()
    _itemsets, lifted, _summary = mine_baskets(
        built,
        min_support=0.5,
        min_confidence=0.5,
        min_lift=3,
        restaurant_specific=False,
        min_restaurant_transactions=1,
    )
    assert lifted.empty
    assert list(lifted.columns) == [
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


def test_invalid_thresholds_and_empty_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="min_support"):
        validate_thresholds(0, 0.3, None, 30)
    with pytest.raises(ValueError, match="min_confidence"):
        validate_thresholds(0.3, 1.5, None, 30)
    with pytest.raises(ValueError, match="min_lift"):
        validate_thresholds(0.3, 0.3, math.nan, 30)
    with pytest.raises(ValueError, match="min_restaurant_transactions"):
        validate_thresholds(0.3, 0.3, None, 0)
    assert main(["--min-support", "0"]) == 1

    empty_orders = _orders([{"id": 1, "restaurant_id": 1, "status": "cancelled"}]).iloc[0:0]
    empty_items = _items([{"order_id": 1, "food_item_id": 1, "quantity": 1}]).iloc[0:0]
    empty_foods = _foods([{"id": 1, "restaurant_id": 1, "name": "A"}]).iloc[0:0]
    for frame, name in (
        (empty_orders, "orders.parquet"),
        (empty_items, "order_items.parquet"),
        (empty_foods, "food_items.parquet"),
    ):
        frame.to_parquet(tmp_path / name, index=False)
    payload = run_mining(
        tmp_path / "orders.parquet",
        tmp_path / "order_items.parquet",
        tmp_path / "food_items.parquet",
        tmp_path,
        0.5,
        0.5,
        None,
        False,
        1,
    )
    assert payload["transactions"]["valid_transactions"] == 0
    assert payload["itemset_count"] == 0
    assert payload["rule_count"] == 0
    assert payload["empty_result"] is True
    itemsets = pd.read_parquet(tmp_path / "association_frequent_itemsets.parquet")
    rules = pd.read_parquet(tmp_path / "association_rules.parquet")
    assert list(itemsets.columns) == [
        "item_ids",
        "item_names",
        "itemset_size",
        "support_count",
        "support",
        "restaurant_scope",
    ]
    assert rules.empty
    metrics = json.loads((tmp_path / "association_mining_metrics.json").read_text(encoding="utf-8"))
    assert "No itemset met min_support" in metrics["empty_result_reason"]


def test_restaurant_filter_does_not_mix_baskets() -> None:
    orders = _orders(
        [{"id": index, "restaurant_id": 1, "status": "completed"} for index in range(1, 4)]
        + [{"id": 9, "restaurant_id": 2, "status": "completed"}]
    )
    items = _items(
        [
            {"order_id": 1, "food_item_id": 1, "quantity": 1},
            {"order_id": 1, "food_item_id": 2, "quantity": 1},
            {"order_id": 2, "food_item_id": 1, "quantity": 1},
            {"order_id": 2, "food_item_id": 2, "quantity": 1},
            {"order_id": 3, "food_item_id": 1, "quantity": 1},
            {"order_id": 9, "food_item_id": 8, "quantity": 1},
            {"order_id": 9, "food_item_id": 9, "quantity": 1},
        ]
    )
    foods = _foods(
        [
            {"id": 1, "restaurant_id": 1, "name": "A"},
            {"id": 2, "restaurant_id": 1, "name": "B"},
            {"id": 8, "restaurant_id": 2, "name": "Y"},
            {"id": 9, "restaurant_id": 2, "name": "Z"},
        ]
    )
    built = build_baskets(orders, items, foods)
    itemsets, rules, summary = mine_baskets(
        built,
        min_support=0.5,
        min_confidence=0.5,
        min_lift=None,
        restaurant_specific=True,
        min_restaurant_transactions=2,
    )
    assert set(itemsets["restaurant_scope"]) == {"1"}
    assert set(rules["restaurant_scope"]) == {"1"}
    assert "8" not in ",".join(itemsets["item_ids"])
    assert summary["scope"]["restaurants_skipped"][0]["restaurant_id"] == "2"


def test_mining_is_deterministic_and_writes_artifacts(tmp_path: Path) -> None:
    orders, items, foods = _known_world()
    orders_path = tmp_path / "orders.parquet"
    items_path = tmp_path / "items.parquet"
    foods_path = tmp_path / "foods.parquet"
    orders.to_parquet(orders_path, index=False)
    items.to_parquet(items_path, index=False)
    foods.to_parquet(foods_path, index=False)
    before = {path.name: path.read_bytes() for path in (orders_path, items_path, foods_path)}
    first = run_mining(orders_path, items_path, foods_path, tmp_path, 0.5, 0.6, None, False, 1)
    itemsets_first = pd.read_parquet(tmp_path / "association_frequent_itemsets.parquet")
    rules_first = pd.read_parquet(tmp_path / "association_rules.parquet")
    second = run_mining(orders_path, items_path, foods_path, tmp_path, 0.5, 0.6, None, False, 1)
    itemsets_second = pd.read_parquet(tmp_path / "association_frequent_itemsets.parquet")
    rules_second = pd.read_parquet(tmp_path / "association_rules.parquet")
    pd.testing.assert_frame_equal(itemsets_first, itemsets_second)
    pd.testing.assert_frame_equal(rules_first, rules_second)
    assert first["rule_count"] == second["rule_count"]
    assert before == {path.name: path.read_bytes() for path in (orders_path, items_path, foods_path)}
    assert itemsets_first["itemset_size"].max() >= 2
