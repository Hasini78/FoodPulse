"""Spark feature tests. They use temporary Parquet files and do not read data/processed."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from etl.transform.feature_engineering import build_customer_features, build_restaurant_features

REFERENCE = date(2026, 10, 11)


def _job():
    path = Path(__file__).resolve().parents[1] / "pyspark" / "jobs" / "feature_aggregations.py"
    spec = importlib.util.spec_from_file_location("foodpulse_spark_features_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stamp(day: int) -> datetime:
    return datetime(2026, 10, day, 12, 0, tzinfo=timezone.utc)


def _tables() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.DataFrame({"id": [1, 2]}),
        "restaurants": pd.DataFrame({"id": [10]}),
        "orders": pd.DataFrame(
            {
                "id": [1, 2, 3],
                "customer_id": [1, 1, 2],
                "restaurant_id": [10, 10, 10],
                "total_amount": [10.0, 30.0, 5.0],
                "discount_used": [0.0, 2.0, 0.0],
                "status": ["completed", "Completed", "cancelled"],
                "order_date": [_stamp(1), _stamp(10), _stamp(10)],
            }
        ),
        "reviews": pd.DataFrame(
            {
                "id": [7, 8],
                "customer_id": [1, 2],
                "restaurant_id": [10, 10],
                "rating": [5, 1],
                "created_at": [_stamp(10), _stamp(2)],
            }
        ),
    }


def _write_inputs(directory: Path, tables: dict[str, pd.DataFrame]) -> None:
    for name, frame in tables.items():
        ready = frame.copy()
        for column in ready.columns:
            if pd.api.types.is_datetime64_any_dtype(ready[column]):
                ready[column] = ready[column].astype("datetime64[us, UTC]")
        ready.to_parquet(directory / f"{name}.parquet", index=False)


def test_missing_file_and_missing_column_fail_before_spark(tmp_path: Path) -> None:
    job = _job()
    tables = _tables()
    orders = tables.pop("orders")
    _write_inputs(tmp_path, tables)
    with pytest.raises(FileNotFoundError, match="orders.parquet"):
        job._validate_inputs(tmp_path)
    orders = orders.drop(columns=["status"])
    orders.to_parquet(tmp_path / "orders.parquet", index=False)
    with pytest.raises(ValueError, match="status"):
        job.run_job(tmp_path, tmp_path / "out", REFERENCE)


def test_same_directory_is_rejected(tmp_path: Path) -> None:
    job = _job()
    _write_inputs(tmp_path, _tables())
    with pytest.raises(ValueError, match="Refusing"):
        job.run_job(tmp_path, tmp_path, REFERENCE)
    assert not (tmp_path / "customer_features.parquet").exists()


def test_empty_orders_leave_null_rates(tmp_path: Path) -> None:
    job = _job()
    tables = _tables()
    tables["orders"] = tables["orders"].iloc[0:0]
    tables["reviews"] = tables["reviews"].iloc[0:0]
    _write_inputs(tmp_path, tables)
    output = tmp_path / "spark_out"
    job.run_job(tmp_path, output, REFERENCE)
    customers = pd.read_parquet(output / "customer_features.parquet")
    assert set(customers["customer_id"]) == {1, 2}
    assert customers["order_frequency"].tolist() == [0, 0]
    assert customers["avg_order_value"].isna().all()
    assert customers["discount_usage_rate"].isna().all()
    assert customers["recency_days"].isna().all()
    restaurants = pd.read_parquet(output / "restaurant_features.parquet")
    assert restaurants.loc[0, "order_volume"] == 0
    assert pd.isna(restaurants.loc[0, "sentiment_label"])
    assert pd.isna(restaurants.loc[0, "sentiment_score"])


def test_aggregates_match_the_pandas_definitions(tmp_path: Path) -> None:
    job = _job()
    tables = _tables()
    tables["reviews"].loc[1, "rating"] = pd.NA
    sentiment = pd.DataFrame(
        {
            "review_id": [7, 8],
            "overall_sentiment": ["positive", "negative"],
            "overall_score": [0.8, -0.4],
        }
    )
    _write_inputs(tmp_path, tables)
    sentiment.to_parquet(tmp_path / "review_sentiment.parquet", index=False)
    output = tmp_path / "spark_out"
    written = job.run_job(tmp_path, output, REFERENCE)
    spark_customers = pd.read_parquet(output / "customer_features.parquet").sort_values("customer_id")
    pandas_customers = build_customer_features(
        tables["customers"], tables["orders"], tables["reviews"], reference_date=REFERENCE
    ).sort_values("customer_id")
    for column in ("order_frequency", "total_spend", "avg_order_value", "review_frequency", "discount_usage_rate"):
        pd.testing.assert_series_equal(
            spark_customers[column].reset_index(drop=True),
            pandas_customers[column].reset_index(drop=True),
            check_dtype=False,
            check_names=False,
        )
    assert int(spark_customers["recency_days"].iloc[0]) == 1
    assert pd.isna(spark_customers["recency_days"].iloc[1])
    spark_restaurants = pd.read_parquet(output / "restaurant_features.parquet")
    pandas_restaurants = build_restaurant_features(
        tables["restaurants"], tables["orders"], tables["reviews"], reference_date=REFERENCE
    )
    assert spark_restaurants.loc[0, "order_volume"] == pandas_restaurants.loc[0, "order_volume"] == 2
    assert spark_restaurants.loc[0, "review_volume"] == 2
    assert spark_restaurants.loc[0, "complaint_count"] == 0
    assert spark_restaurants.loc[0, "avg_rating"] == pytest.approx(5.0)
    assert pd.isna(spark_restaurants.loc[0, "sentiment_score"])
    activity = pd.read_parquet(output / "restaurant_activity.parquet")
    assert activity.loc[0, "total_spend"] == pytest.approx(40.0)
    assert activity.loc[0, "avg_order_value"] == pytest.approx(20.0)
    assert activity.loc[0, "customer_count"] == 1
    counts = pd.read_parquet(output / "restaurant_sentiment_counts.parquet")
    assert counts.loc[0, "positive_count"] == 1
    assert counts.loc[0, "negative_count"] == 1
    assert counts.loc[0, "positive_proportion"] == pytest.approx(0.5)
    assert written["restaurant_sentiment_counts"] == 1
    assert (tmp_path / "customer_features.parquet").is_file() is False
