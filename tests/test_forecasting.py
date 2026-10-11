"""Tests for demand aggregation, chronological forecasts, and the CLI."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from mining.forecasting.evaluate import evaluate_series, regression_metrics, split_holdout
from mining.forecasting.features import aggregate_demand, feature_vector
from mining.forecasting.models import ridge_forecast, seasonal_naive
from mining.forecasting.run_forecast import forecast_frames, main

REFERENCE = date(2026, 3, 1)


def _orders(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _items(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _foods() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": 1, "restaurant_id": 1},
            {"id": 2, "restaurant_id": 1},
            {"id": 3, "restaurant_id": 2},
        ]
    )


def _daily_orders(days: int, restaurant_id: int = 1, status: str = "completed") -> pd.DataFrame:
    rows = []
    for offset in range(days):
        stamp = pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=offset)
        rows.append(
            {
                "id": offset + 1,
                "restaurant_id": restaurant_id,
                "status": status,
                "order_date": stamp.isoformat(),
                "total_amount": 500.0,
            }
        )
    return _orders(rows)


def test_daily_and_weekly_aggregation_do_not_use_order_totals() -> None:
    orders = _orders(
        [
            {"id": 1, "restaurant_id": 1, "status": "completed", "order_date": "2026-01-05T00:00:00+00:00", "total_amount": 500.0},
            {"id": 2, "restaurant_id": 1, "status": "completed", "order_date": "2026-01-06T00:00:00+00:00", "total_amount": 800.0},
            {"id": 3, "restaurant_id": 1, "status": "cancelled", "order_date": "2026-01-06T00:00:00+00:00", "total_amount": 900.0},
            {"id": 4, "restaurant_id": 1, "status": "pending", "order_date": "2026-01-07T00:00:00+00:00", "total_amount": 100.0},
            {"id": 5, "restaurant_id": 1, "status": "completed", "order_date": "2026-01-12T00:00:00+00:00", "total_amount": 50.0},
            {"id": 6, "restaurant_id": 1, "status": "completed", "order_date": "2026-03-02T00:00:00+00:00", "total_amount": 50.0},
        ]
    )
    items = _items(
        [
            {"order_id": 1, "food_item_id": 1, "quantity": 2},
            {"order_id": 2, "food_item_id": 1, "quantity": 4},
            {"order_id": 3, "food_item_id": 1, "quantity": 9},
            {"order_id": 5, "food_item_id": 2, "quantity": 1},
            {"order_id": 5, "food_item_id": 3, "quantity": 7},
        ]
    )
    restaurants, food, _notes = aggregate_demand(orders, items, _foods(), REFERENCE, "daily")
    restaurant = restaurants.loc[restaurants["restaurant_id"] == "1"].sort_values("period_start")
    assert int(restaurant.loc[restaurant["period_start"] == pd.Timestamp("2026-01-06", tz="UTC"), "actual_demand"].iloc[0]) == 1
    assert pd.Timestamp("2026-01-04", tz="UTC") not in set(restaurant["period_start"])
    gap = restaurant.loc[restaurant["period_start"] == pd.Timestamp("2026-01-08", tz="UTC"), "actual_demand"]
    assert float(gap.iloc[0]) == 0.0
    assert pd.Timestamp("2026-03-02", tz="UTC") not in set(restaurant["period_start"])
    item = food.loc[food["food_item_id"] == "1"]
    assert float(item.loc[item["period_start"] == pd.Timestamp("2026-01-05", tz="UTC"), "actual_demand"].iloc[0]) == 2.0
    assert float(item.loc[item["period_start"] == pd.Timestamp("2026-01-06", tz="UTC"), "actual_demand"].iloc[0]) == 4.0
    assert "3" not in set(food["food_item_id"])
    weekly_restaurants, _weekly_items, _notes = aggregate_demand(orders, items, _foods(), REFERENCE, "weekly")
    week = weekly_restaurants.loc[weekly_restaurants["period_start"] == pd.Timestamp("2026-01-05", tz="UTC"), "actual_demand"]
    assert int(week.iloc[0]) == 2


def test_missing_columns_raise() -> None:
    with pytest.raises(ValueError, match="orders"):
        aggregate_demand(pd.DataFrame({"id": [1]}), _items([]), _foods(), REFERENCE, "daily")


def test_feature_row_excludes_the_current_value() -> None:
    when = pd.Timestamp("2026-01-04", tz="UTC")
    row = feature_vector([1.0, 2.0, 3.0], when, "daily")
    assert row[0] == 3.0
    assert row[3] == float(when.weekday())


def test_short_series_is_skipped_and_forecasts_stay_non_negative(tmp_path: Path) -> None:
    orders = _daily_orders(10)
    items = _items([{"order_id": index, "food_item_id": 1, "quantity": 1} for index in range(1, 11)])
    with pytest.raises(RuntimeError, match="enough history"):
        forecast_frames(orders, items, _foods(), date(2026, 1, 10), 7, "daily", "ridge", 42, 28)
    long_orders = _daily_orders(40)
    long_items = _items([{"order_id": index, "food_item_id": 1, "quantity": 1} for index in range(1, 41)])
    result = forecast_frames(long_orders, long_items, _foods(), date(2026, 2, 9), 7, "daily", "ridge", 42, 28)
    assert (result["forecasts"]["predicted_demand"] >= 0).all()
    assert set(result["forecasts"]["model_name"]) <= {"ridge", "seasonal_naive"}
    assert set(result["forecasts"]["forecast_role"]) == {"holdout", "forward"}


def test_holdout_is_the_series_tail_and_future_actuals_are_not_training_inputs() -> None:
    values = [1.0] * 30 + [100.0] * 7
    dates = list(pd.date_range("2026-01-01", periods=len(values), freq="D", tz="UTC"))
    split = split_holdout(values, dates, 7, 14)
    assert split is not None
    train, _train_dates, test, _test_dates = split
    assert train == [1.0] * 30
    assert test == [100.0] * 7
    scored = evaluate_series(values, dates, 7, "daily", 14, 42)
    assert scored is not None
    assert max(scored["model_holdout"]) < 20
    assert max(scored["baseline_holdout"]) < 20
    naive = seasonal_naive([10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 8, "daily")
    assert naive[0] == 10.0
    assert naive[7] == 10.0
    ridge_values, name = ridge_forecast([1.0] * 30, dates[:30], 7, "daily", 42)
    assert name == "ridge"
    assert all(value >= 0 for value in ridge_values)
    assert max(ridge_values) < 20


def test_wape_is_null_when_actual_demand_is_zero() -> None:
    zero = regression_metrics([0.0, 0.0], [1.0, 2.0])
    assert zero["wape"] is None
    assert zero["mae"] == 1.5
    assert regression_metrics([2.0, 2.0], [0.0, 0.0])["wape"] == 1.0


def test_cli_rejects_invalid_arguments_and_missing_files(tmp_path: Path) -> None:
    assert main(["--horizon", "0"]) == 1
    assert main(["--aggregation", "hourly"]) == 1
    assert main(["--orders", str(tmp_path / "missing.parquet"), "--reference-date", "2026-10-11"]) == 1
    orders = _daily_orders(40)
    items = _items([{"order_id": index, "food_item_id": 1, "quantity": 2} for index in range(1, 41)])
    foods = _foods()
    orders_path = tmp_path / "orders.parquet"
    items_path = tmp_path / "order_items.parquet"
    foods_path = tmp_path / "food_items.parquet"
    orders.to_parquet(orders_path, index=False)
    items.to_parquet(items_path, index=False)
    foods.to_parquet(foods_path, index=False)
    before = orders_path.read_bytes()
    output = tmp_path / "out"
    artifacts = tmp_path / "artifacts"
    code = main(
        [
            "--orders",
            str(orders_path),
            "--order-items",
            str(items_path),
            "--food-items",
            str(foods_path),
            "--output-dir",
            str(output),
            "--artifacts-dir",
            str(artifacts),
            "--reference-date",
            "2026-02-09",
            "--horizon",
            "7",
            "--aggregation",
            "daily",
            "--seed",
            "42",
            "--min-history",
            "28",
        ]
    )
    assert code == 0
    assert orders_path.read_bytes() == before
    assert (output / "demand_forecasts.parquet").is_file()
    assert (output / "demand_forecast_history.parquet").is_file()
    assert (output / "demand_forecast_metrics.json").is_file()
    assert (artifacts / "demand_forecast_holdout.png").is_file()
