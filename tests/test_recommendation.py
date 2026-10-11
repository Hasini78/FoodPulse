"""Tests for hybrid food and restaurant recommendations."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mining.recommendation.candidates import build_context, load_association_rules
from mining.recommendation.evaluate import evaluate_holdout
from mining.recommendation.ranker import FOOD_COLUMNS, RESTAURANT_COLUMNS, recommend
from mining.recommendation.run_recommendations import main, run_recommendations

REFERENCE = "2026-10-11"


def _customers(*ids: int) -> pd.DataFrame:
    return pd.DataFrame({"customer_id": list(ids), "email": ["secret@example.com"] * len(ids)})


def _restaurants() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": 1, "cuisine_type": "Italian", "is_active": True, "name": "A", "phone": "555"},
            {"id": 2, "cuisine_type": "Mexican", "is_active": True, "name": "B", "phone": "555"},
        ]
    )


def _foods() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": 1, "restaurant_id": 1, "is_available": True, "name": "Pasta"},
            {"id": 2, "restaurant_id": 1, "is_available": True, "name": "Salad"},
            {"id": 3, "restaurant_id": 2, "is_available": True, "name": "Taco"},
            {"id": 4, "restaurant_id": 1, "is_available": True, "name": "Pizza"},
            {"id": 11, "restaurant_id": 1, "is_available": True, "name": "Soup"},
        ]
    )


def _orders(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _items(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _reviews(rows: list[dict] | None = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["id", "customer_id", "restaurant_id", "rating", "created_at"])
    return pd.DataFrame(rows)


def _sentiment(rows: list[dict] | None = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["review_id", "overall_score"])
    return pd.DataFrame(rows)


def _rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"antecedent_ids": "1", "consequent_ids": "2", "confidence": 0.8, "lift": 2.0, "support": 0.2},
            {"antecedent_ids": "1", "consequent_ids": "3", "confidence": 0.9, "lift": 3.0, "support": 0.2},
        ]
    )


def _world():
    customers = _customers(1, 2)
    orders = _orders(
        [
            {"id": 10, "customer_id": 1, "restaurant_id": 1, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 11, "customer_id": 1, "restaurant_id": 1, "status": "completed", "order_date": "2026-03-01T00:00:00+00:00"},
            {"id": 12, "customer_id": 1, "restaurant_id": 1, "status": "completed", "order_date": "2026-05-01T00:00:00+00:00"},
            {"id": 13, "customer_id": 1, "restaurant_id": 1, "status": "cancelled", "order_date": "2026-09-01T00:00:00+00:00"},
        ]
    )
    items = _items(
        [
            {"order_id": 10, "food_item_id": 1},
            {"order_id": 11, "food_item_id": 1},
            {"order_id": 12, "food_item_id": 4},
            {"order_id": 13, "food_item_id": 2},
            {"order_id": 12, "food_item_id": 99},
            {"order_id": 12, "food_item_id": 3},
        ]
    )
    return customers, orders, items


def test_history_uses_association_and_skips_one_time_purchases(tmp_path: Path) -> None:
    customers, orders, items = _world()
    foods = _foods()
    rules_path = tmp_path / "rules.parquet"
    _rules().to_parquet(rules_path, index=False)
    rules, warnings = load_association_rules(rules_path, foods)
    assert not any("not found" in warning for warning in warnings)
    context = build_context(customers, orders, items, foods, _restaurants(), _reviews(), _sentiment(), pd.Timestamp(REFERENCE).date())
    food, restaurants = recommend(context, rules, food_k=5, restaurant_k=2)
    personal = food.loc[food["customer_id"] == "1"]
    chosen = set(personal["food_item_id"])
    assert "2" in chosen
    assert "4" not in chosen
    assert "3" not in chosen
    assert "99" not in chosen
    row = food.loc[food["food_item_id"] == "2"].iloc[0]
    assert row["restaurant_id"] == "1"
    assert row["reason"] in {
        "associated with a previously purchased item",
        "frequently purchased cuisine",
        "highly rated in preferred cuisine",
        "previously reordered item",
    }
    assert food.duplicated(["customer_id", "food_item_id"]).sum() == 0
    assert list(personal["rank"]) == list(range(1, len(personal) + 1))
    assert "email" not in food.columns
    assert "phone" not in restaurants.columns


def test_missing_catalog_item_is_skipped() -> None:
    customers, orders, items = _world()
    foods = _foods()
    rules = pd.DataFrame(
        [
            {"antecedent_id": "1", "consequent_id": "999", "restaurant_id": "1", "confidence": 1.0, "lift": 2.0, "support": 0.1, "association_strength": 1.0},
            {"antecedent_id": "1", "consequent_id": "2", "restaurant_id": "1", "confidence": 0.5, "lift": 1.5, "support": 0.1, "association_strength": 0.4},
        ]
    )
    context = build_context(customers, orders, items, foods, _restaurants(), _reviews(), _sentiment(), pd.Timestamp(REFERENCE).date())
    food, _restaurants_out = recommend(context, rules, food_k=5, restaurant_k=2)
    chosen = set(food.loc[food["customer_id"] == "1", "food_item_id"])
    assert "999" not in chosen
    assert "2" in chosen


def test_cross_restaurant_rule_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "rules.parquet"
    _rules().to_parquet(path, index=False)
    rules, warnings = load_association_rules(path, _foods())
    assert set(rules["consequent_id"]) == {"2"}
    assert any("skipped" in warning for warning in warnings)


def test_missing_rules_and_missing_sentiment_do_not_crash(tmp_path: Path) -> None:
    rules, warnings = load_association_rules(tmp_path / "missing.parquet", _foods())
    assert rules.empty
    assert any("Association rules were not found" in warning for warning in warnings)
    customers, orders, items = _world()
    context = build_context(customers, orders, items, _foods(), _restaurants(), _reviews(), _sentiment(), pd.Timestamp(REFERENCE).date())
    food, _restaurants_out = recommend(context, rules, 3, 2)
    assert not food.empty
    assert food["reason"].notna().all()


def test_new_customer_gets_general_picks() -> None:
    customers = _customers(5)
    orders = _orders([{"id": 1, "customer_id": 1, "restaurant_id": 1, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"}]).iloc[0:0]
    items = _items([{"order_id": 1, "food_item_id": 1}]).iloc[0:0]
    context = build_context(customers, orders, items, _foods(), _restaurants(), _reviews(), _sentiment(), pd.Timestamp(REFERENCE).date())
    food, restaurants = recommend(context, pd.DataFrame(columns=["antecedent_id", "consequent_id", "restaurant_id", "confidence", "lift", "support", "association_strength"]), 3, 2)
    assert not food.empty
    assert set(food["reason"]) == {"general pick for limited history"}
    assert set(restaurants["reason"]) == {"general pick for limited history"}


def test_tie_break_prefers_lower_item_id() -> None:
    customers = _customers(1)
    orders = _orders(
        [
            {"id": index, "customer_id": 1, "restaurant_id": 1, "status": "completed", "order_date": f"2026-0{index}-01T00:00:00+00:00"}
            for index in (1, 2, 3)
        ]
    )
    items = _items([{"order_id": index, "food_item_id": 4} for index in (1, 2, 3)])
    context = build_context(customers, orders, items, _foods(), _restaurants(), _reviews(), _sentiment(), pd.Timestamp(REFERENCE).date())
    food, _restaurants_out = recommend(context, pd.DataFrame(columns=["antecedent_id", "consequent_id", "restaurant_id", "confidence", "lift", "support", "association_strength"]), 5, 1)
    tied = food.loc[food["food_item_id"].isin(["1", "2", "11"])].sort_values("rank")
    assert tied.iloc[0]["food_item_id"] == "1"
    assert list(tied["food_item_id"]) == ["1", "2", "11"]


def test_future_order_is_excluded_from_preferences() -> None:
    customers = _customers(1)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "restaurant_id": 1, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "restaurant_id": 2, "status": "completed", "order_date": "2026-08-01T00:00:00+00:00"},
        ]
    )
    items = _items([{"order_id": 1, "food_item_id": 1}, {"order_id": 2, "food_item_id": 3}])
    early = build_context(
        customers,
        orders,
        items,
        _foods(),
        _restaurants(),
        _reviews(),
        _sentiment(),
        pd.Timestamp(REFERENCE).date(),
        as_of=pd.Timestamp("2026-07-01T00:00:00+00:00"),
    )
    assert set(early["purchases"]["food_item_id"]) == {"1"}
    metrics = evaluate_holdout(customers, orders, items, _foods(), _restaurants(), _reviews(), _sentiment(), pd.Timestamp(REFERENCE).date(), 5, 3)
    assert metrics["food_eligible_customers"] == 1
    assert metrics["restaurant_eligible_customers"] == 1
    assert metrics["association_in_holdout"] is False
    assert metrics["food_hit_rate_at_k"] is not None


def test_empty_inputs_keep_the_schema(tmp_path: Path) -> None:
    customers = _customers(1).iloc[0:0]
    orders = _orders([{"id": 1, "customer_id": 1, "restaurant_id": 1, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"}]).iloc[0:0]
    items = _items([{"order_id": 1, "food_item_id": 1}]).iloc[0:0]
    foods = _foods().iloc[0:0]
    restaurants = _restaurants().iloc[0:0]
    for frame, name in (
        (customers, "customers.parquet"),
        (orders, "orders.parquet"),
        (items, "items.parquet"),
        (foods, "foods.parquet"),
        (restaurants, "restaurants.parquet"),
        (_reviews(), "reviews.parquet"),
        (_sentiment(), "sentiment.parquet"),
    ):
        frame.to_parquet(tmp_path / name, index=False)
    payload = run_recommendations(
        tmp_path / "customers.parquet",
        tmp_path / "orders.parquet",
        tmp_path / "items.parquet",
        tmp_path / "foods.parquet",
        tmp_path / "restaurants.parquet",
        tmp_path / "reviews.parquet",
        tmp_path / "sentiment.parquet",
        tmp_path / "missing_rules.parquet",
        tmp_path,
        tmp_path / "artifacts",
        REFERENCE,
        5,
        3,
        2,
    )
    food = pd.read_parquet(tmp_path / "food_recommendations.parquet")
    restaurants_out = pd.read_parquet(tmp_path / "restaurant_recommendations.parquet")
    assert list(food.columns) == FOOD_COLUMNS
    assert list(restaurants_out.columns) == RESTAURANT_COLUMNS
    assert food.empty and restaurants_out.empty
    assert payload["empty_result"] is True
    assert main(["--food-k", "0"]) == 1


def test_scores_are_deterministic(tmp_path: Path) -> None:
    customers, orders, items = _world()
    foods = _foods()
    rules = tmp_path / "rules.parquet"
    _rules().to_parquet(rules, index=False)
    paths = {}
    for frame, name in (
        (customers, "customers.parquet"),
        (orders, "orders.parquet"),
        (items, "items.parquet"),
        (foods, "foods.parquet"),
        (_restaurants(), "restaurants.parquet"),
        (_reviews([{"id": 1, "customer_id": 1, "restaurant_id": 1, "rating": 5, "created_at": "2026-02-01T00:00:00+00:00"}]), "reviews.parquet"),
        (_sentiment([{"review_id": 1, "overall_score": 0.4}]), "sentiment.parquet"),
    ):
        path = tmp_path / name
        frame.to_parquet(path, index=False)
        paths[name] = path
    before = {name: path.read_bytes() for name, path in paths.items()}
    first = run_recommendations(*paths.values(), rules, tmp_path, tmp_path / "artifacts", REFERENCE, 5, 3, 2)
    food_first = pd.read_parquet(tmp_path / "food_recommendations.parquet")
    second = run_recommendations(*paths.values(), rules, tmp_path, tmp_path / "artifacts", REFERENCE, 5, 3, 2)
    food_second = pd.read_parquet(tmp_path / "food_recommendations.parquet")
    pd.testing.assert_frame_equal(food_first, food_second)
    assert first["counts"]["food_recommendations"] == second["counts"]["food_recommendations"]
    assert before == {name: path.read_bytes() for name, path in paths.items()}
