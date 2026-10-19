"""Metric definitions used by the dashboard charts."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.dashboard_metrics import aspect_counts, completed_metrics, forecast_window


def test_completed_revenue_excludes_other_statuses_and_builds_months() -> None:
    orders = pd.DataFrame(
        {
            "status": ["Completed", "cancelled", "completed"],
            "total_amount": [10.0, 100.0, 30.0],
            "order_date": [
                datetime(2026, 9, 2, tzinfo=timezone.utc),
                datetime(2026, 9, 3, tzinfo=timezone.utc),
                datetime(2026, 10, 4, tzinfo=timezone.utc),
            ],
        }
    )
    metrics = completed_metrics(orders, start="2026-10-01", end="2026-10-31")
    assert metrics["completed_orders"] == 1
    assert metrics["completed_revenue"] == pytest.approx(30.0)
    assert metrics["average_order_value"] == pytest.approx(30.0)
    assert metrics["monthly"] == [{"month": "2026-10", "completed_orders": 1, "completed_revenue": 30.0}]


def test_invalid_date_filter_and_empty_completed_orders() -> None:
    orders = pd.DataFrame({"status": ["cancelled"], "total_amount": [5.0], "order_date": [datetime(2026, 1, 1, tzinfo=timezone.utc)]})
    metrics = completed_metrics(orders)
    assert metrics["completed_orders"] == 0
    assert metrics["completed_revenue"] is None
    assert metrics["monthly"] == []
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        completed_metrics(orders, start="October")


def test_aspect_counts_skip_missing_columns_and_forecast_has_no_intervals() -> None:
    aspects = aspect_counts(pd.DataFrame({"food_sent": ["positive", "positive", None], "price_sent": ["negative", "negative", "positive"]}))
    food = [row for row in aspects if row["aspect"] == "food"]
    assert sum(row["count"] for row in food) == 3
    assert all(row["aspect"] != "service" for row in aspects)
    window = forecast_window(
        pd.DataFrame(
            {
                "level": ["restaurant"],
                "forecast_role": ["forward"],
                "model_name": ["ridge"],
                "aggregation": ["daily"],
                "forecast_date": [datetime(2026, 10, 12, tzinfo=timezone.utc)],
                "restaurant_id": ["3"],
                "horizon": [7],
            }
        )
    )
    assert window["intervals"] is None
    assert window["available"] is True
    assert window["horizon"] == 7
    assert forecast_window(pd.DataFrame())["available"] is False
