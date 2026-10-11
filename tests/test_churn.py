"""Tests for inactivity features, categories, and churn artifacts."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from mining.churn.analyze import classify, validate_thresholds
from mining.churn.features import build_behavior
from mining.churn.run_analysis import main, run_analysis

REFERENCE = "2026-10-11"


def _customers(*ids: int) -> pd.DataFrame:
    return pd.DataFrame({"customer_id": list(ids), "name": ["Secret"] * len(ids), "email": ["a@example.com"] * len(ids)})


def _orders(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column, default in (("discount_used", 0.0), ("total_amount", 10.0)):
        if column not in frame.columns:
            frame[column] = default
    return frame


def _reviews(rows: list[dict] | None = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["id", "customer_id", "rating", "created_at"])
    return pd.DataFrame(rows)


def _sentiment(rows: list[dict] | None = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["review_id", "overall_score"])
    return pd.DataFrame(rows)


def _build(customers, orders, reviews=None, sentiment=None, window=45):
    return build_behavior(customers, orders, reviews if reviews is not None else _reviews(), sentiment if sentiment is not None else _sentiment(), pd.Timestamp(REFERENCE).date(), window)


def test_cancelled_and_pending_orders_do_not_reset_inactivity() -> None:
    customers = _customers(1)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "total_amount": 20.0, "status": "completed", "order_date": "2026-07-13T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "total_amount": 99.0, "status": "cancelled", "order_date": "2026-10-10T00:00:00+00:00"},
            {"id": 3, "customer_id": 1, "total_amount": 50.0, "status": "pending", "order_date": "2026-10-11T00:00:00+00:00"},
        ]
    )
    behavior, stats = _build(customers, orders)
    assert int(behavior.loc[0, "inactivity_days"]) == 90
    assert float(behavior.loc[0, "total_spend"]) == 20.0
    assert int(behavior.loc[0, "order_frequency"]) == 1
    assert stats["non_completed_orders_ignored"] == 2
    assert stats["completed_orders_used"] == 1


def test_spend_ignores_duplicate_orders_and_is_not_joined_to_items() -> None:
    customers = _customers(1)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "total_amount": 10.0, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 1, "customer_id": 1, "total_amount": 1000.0, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "total_amount": 5.0, "status": "completed", "order_date": "2026-06-01T00:00:00+00:00"},
        ]
    )
    behavior, stats = _build(customers, orders)
    assert float(behavior.loc[0, "total_spend"]) == 15.0
    assert int(behavior.loc[0, "order_frequency"]) == 2
    assert stats["duplicate_order_ids_removed"] == 1
    assert len(behavior) == 1


def test_inactivity_boundaries_and_insufficient_history() -> None:
    customers = _customers(1, 2, 3, 4, 5)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "status": "completed", "order_date": "2026-08-28T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 3, "customer_id": 2, "status": "completed", "order_date": "2026-08-27T00:00:00+00:00"},
            {"id": 4, "customer_id": 2, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 5, "customer_id": 3, "status": "completed", "order_date": "2026-07-14T00:00:00+00:00"},
            {"id": 6, "customer_id": 3, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 7, "customer_id": 4, "status": "completed", "order_date": "2026-07-13T00:00:00+00:00"},
            {"id": 8, "customer_id": 4, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 9, "customer_id": 5, "status": "completed", "order_date": "2026-10-01T00:00:00+00:00"},
        ]
    )
    behavior, _stats = _build(customers, orders)
    classified = classify(behavior, inactivity_days=90, at_risk_days=45, low_frequency_max=1)
    categories = classified.set_index("customer_id")["risk_category"].to_dict()
    assert categories[1] == "active"
    assert categories[2] == "at_risk"
    assert categories[3] == "at_risk"
    assert categories[4] == "churned_under_definition"
    assert categories[5] == "insufficient_history"
    assert pd.isna(classified.set_index("customer_id").loc[5, "risk_score"])
    assert "name" not in classified.columns
    assert "email" not in classified.columns


def test_known_score_and_optional_missing_features() -> None:
    customers = _customers(1)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "total_amount": 30.0, "discount_used": 0.0, "status": "completed", "order_date": "2026-01-13T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "total_amount": 30.0, "discount_used": 0.0, "status": "completed", "order_date": "2026-04-14T00:00:00+00:00"},
            {"id": 3, "customer_id": 1, "total_amount": 30.0, "discount_used": 0.0, "status": "completed", "order_date": "2026-07-13T00:00:00+00:00"},
        ]
    )
    behavior, _stats = _build(customers, orders)
    classified = classify(behavior, 90, 45, 2)
    row = classified.iloc[0]
    assert row["risk_category"] == "churned_under_definition"
    assert int(row["inactivity_days"]) == 90
    assert "low_order_frequency" not in row["reason_codes"]
    assert "current_gap_exceeds_typical" not in row["reason_codes"]
    assert "recent_frequency_decline" in row["reason_codes"]
    assert "low_rating" not in row["reason_codes"]
    assert "negative_sentiment" not in row["reason_codes"]
    assert row["risk_score"] == pytest.approx(70.0)
    assert pd.isna(row["avg_rating"])
    assert pd.isna(row["avg_sentiment_score"])


def test_low_rating_and_negative_sentiment_add_points_only_when_present() -> None:
    customers = _customers(1, 2)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "status": "completed", "order_date": "2026-10-01T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 3, "customer_id": 2, "status": "completed", "order_date": "2026-10-01T00:00:00+00:00"},
            {"id": 4, "customer_id": 2, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
        ]
    )
    reviews = _reviews(
        [
            {"id": 10, "customer_id": 1, "rating": 1, "created_at": "2026-10-02T00:00:00+00:00"},
            {"id": 11, "customer_id": 2, "rating": 5, "created_at": "2026-10-02T00:00:00+00:00"},
        ]
    )
    sentiment = _sentiment(
        [
            {"review_id": 10, "overall_score": -0.2},
            {"review_id": 11, "overall_score": 0.4},
            {"review_id": 10, "overall_score": -0.9},
        ]
    )
    behavior, _stats = _build(customers, orders, reviews, sentiment)
    classified = classify(behavior, 90, 45, 1).set_index("customer_id")
    assert "low_rating" in classified.loc[1, "reason_codes"]
    assert "negative_sentiment" in classified.loc[1, "reason_codes"]
    assert "low_rating" not in classified.loc[2, "reason_codes"]
    assert "negative_sentiment" not in classified.loc[2, "reason_codes"]
    assert classified.loc[1, "risk_score"] == pytest.approx(classified.loc[2, "risk_score"] + 20)
    assert float(classified.loc[1, "avg_sentiment_score"]) == pytest.approx(-0.2)


def test_customers_without_qualifying_orders_are_excluded() -> None:
    customers = _customers(1, 2)
    orders = _orders(
        [
            {"id": 1, "customer_id": 2, "status": "pending", "order_date": "2026-09-01T00:00:00+00:00"},
            {"id": 2, "customer_id": 9, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00", "total_amount": 80.0},
        ]
    )
    behavior, stats = _build(customers, orders)
    assert behavior.empty
    assert stats["customers_without_completed_orders"] == 2
    assert stats["orders_for_unknown_customers"] == 1
    assert stats["completed_orders_used"] == 0


def test_orders_after_the_reference_date_are_ignored() -> None:
    customers = _customers(1)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "total_amount": 10.0, "status": "completed", "order_date": "2026-07-01T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "total_amount": 40.0, "status": "completed", "order_date": "2026-10-12T00:00:00+00:00"},
        ]
    )
    behavior, stats = _build(customers, orders)
    assert float(behavior.loc[0, "total_spend"]) == 10.0
    assert int(behavior.loc[0, "order_frequency"]) == 1
    assert stats["orders_after_reference_ignored"] == 1


def test_invalid_thresholds_and_empty_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at_risk_days"):
        validate_thresholds(90, 90, 4)
    with pytest.raises(ValueError, match="inactivity_days"):
        validate_thresholds(0, 45, 4)
    assert main(["--inactivity-days", "0"]) == 1

    customers = _customers(1).iloc[0:0]
    orders = _orders([{"id": 1, "customer_id": 1, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"}]).iloc[0:0]
    reviews = _reviews()
    sentiment = _sentiment()
    for frame, name in (
        (customers, "customers.parquet"),
        (orders, "orders.parquet"),
        (reviews, "reviews.parquet"),
        (sentiment, "sentiment.parquet"),
    ):
        frame.to_parquet(tmp_path / name, index=False)
    payload = run_analysis(
        tmp_path / "customers.parquet",
        tmp_path / "orders.parquet",
        tmp_path / "reviews.parquet",
        tmp_path / "sentiment.parquet",
        tmp_path,
        tmp_path / "artifacts",
        REFERENCE,
        90,
        45,
        4,
    )
    risk = pd.read_parquet(tmp_path / "customer_churn_risk.parquet")
    summary = pd.read_parquet(tmp_path / "customer_churn_summary.parquet")
    assert risk.empty
    assert "risk_score" in risk.columns
    assert "risk_category" in risk.columns
    assert summary.empty
    assert payload["counts"]["eligible_customers"] == 0
    assert math.isfinite(payload["thresholds"]["inactivity_days"])


def test_artifacts_are_deterministic_and_inputs_stay_unchanged(tmp_path: Path) -> None:
    customers = _customers(1, 2)
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "total_amount": 12.0, "status": "completed", "order_date": "2026-09-01T00:00:00+00:00"},
            {"id": 2, "customer_id": 1, "total_amount": 12.0, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
            {"id": 3, "customer_id": 2, "total_amount": 8.0, "status": "completed", "order_date": "2026-05-01T00:00:00+00:00"},
            {"id": 4, "customer_id": 2, "total_amount": 8.0, "status": "completed", "order_date": "2026-01-01T00:00:00+00:00"},
        ]
    )
    reviews = _reviews([{"id": 1, "customer_id": 2, "rating": 2, "created_at": "2026-05-02T00:00:00+00:00"}])
    sentiment = _sentiment([{"review_id": 1, "overall_score": -0.4}])
    paths = {}
    for frame, name in (
        (customers, "customers.parquet"),
        (orders, "orders.parquet"),
        (reviews, "reviews.parquet"),
        (sentiment, "sentiment.parquet"),
    ):
        path = tmp_path / name
        frame.to_parquet(path, index=False)
        paths[name] = path
    before = {name: path.read_bytes() for name, path in paths.items()}
    first = run_analysis(*paths.values(), tmp_path, tmp_path / "artifacts", REFERENCE, 90, 45, 4)
    risk_first = pd.read_parquet(tmp_path / "customer_churn_risk.parquet")
    second = run_analysis(*paths.values(), tmp_path, tmp_path / "artifacts", REFERENCE, 90, 45, 4)
    risk_second = pd.read_parquet(tmp_path / "customer_churn_risk.parquet")
    pd.testing.assert_frame_equal(risk_first, risk_second)
    assert first["category_distribution"] == second["category_distribution"]
    assert before == {name: path.read_bytes() for name, path in paths.items()}
    assert set(risk_first["risk_category"]).issubset({"active", "at_risk", "churned_under_definition", "insufficient_history"})
    assert (tmp_path / "artifacts" / "customer_churn_categories.png").is_file()
