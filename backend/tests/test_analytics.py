"""Dashboard aggregates over temporary Parquet files and an in-memory database."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db.session import Base
from app.models import Customer, Location, Order, Restaurant, Review
from app.services import analytics_service, stats_service


def _write(directory: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(directory / name, index=False)


def _processed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    return tmp_path


def test_overview_completed_average_and_sentiment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _processed(tmp_path, monkeypatch)
    _write(directory, "restaurants.parquet", pd.DataFrame({"id": [1]}))
    _write(directory, "customers.parquet", pd.DataFrame({"id": [1, 2]}))
    _write(directory, "reviews.parquet", pd.DataFrame({"id": [1]}))
    _write(
        directory,
        "orders.parquet",
        pd.DataFrame(
            {
                "id": [1, 2, 3],
                "status": ["Completed", "cancelled", None],
                "total_amount": [10.0, 100.0, 50.0],
            }
        ),
    )
    _write(
        directory,
        "review_sentiment.parquet",
        pd.DataFrame({"review_id": [1, 2], "overall_sentiment": ["positive", "negative"], "overall_score": [0.8, -0.4]}),
    )
    payload = analytics_service.overview()
    assert payload["restaurants"] == 1
    assert payload["customers"] == 2
    assert payload["completed_orders"] == 1
    assert payload["average_order_value"] == pytest.approx(10.0)
    labels = {item["label"]: item for item in payload["sentiment"]}
    assert labels["positive"]["count"] == 1
    assert labels["positive"]["proportion"] == pytest.approx(0.5)


def test_missing_orders_is_unavailable_and_bad_schema_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _processed(tmp_path, monkeypatch)
    _write(directory, "restaurants.parquet", pd.DataFrame({"id": [1]}))
    payload = analytics_service.overview()
    assert payload["restaurants"] == 1
    assert payload["orders"] is None
    assert any("orders.parquet" in item for item in payload["unavailable"])
    _write(directory, "orders.parquet", pd.DataFrame({"id": [1], "status": ["completed"]}))
    with pytest.raises(analytics_service.AnalyticsDataError, match="total_amount"):
        analytics_service.restaurant_performance()


def test_empty_orders_leave_value_null(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _processed(tmp_path, monkeypatch)
    _write(directory, "orders.parquet", pd.DataFrame({"id": [], "status": [], "total_amount": [], "restaurant_id": []}))
    _write(directory, "restaurants.parquet", pd.DataFrame({"id": [1], "name": ["North"], "cuisine_type": ["Thai"]}))
    payload = analytics_service.restaurant_performance()
    assert payload["items"][0]["completed_orders"] == 0
    assert payload["items"][0]["avg_order_value"] is None
    assert payload["items"][0]["avg_rating"] is None


def test_restaurant_metrics_null_ratings_and_sort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _processed(tmp_path, monkeypatch)
    _write(
        directory,
        "orders.parquet",
        pd.DataFrame(
            {
                "restaurant_id": [1, 1, 2],
                "status": ["completed", "completed", "cancelled"],
                "total_amount": [10.0, 30.0, 99.0],
            }
        ),
    )
    _write(
        directory,
        "restaurants.parquet",
        pd.DataFrame({"id": [1, 2], "name": ["North", "South"], "cuisine_type": ["Thai", "Indian"]}),
    )
    _write(
        directory,
        "restaurant_features.parquet",
        pd.DataFrame(
            {
                "restaurant_id": [1],
                "avg_rating": [4.5],
                "review_volume": [2],
                "order_volume": [2],
                "feature_reference_date": ["2026-10-11"],
            }
        ),
    )
    payload = analytics_service.restaurant_performance(sort="total_spend", cuisine="Thai")
    assert payload["total"] == 1
    assert payload["items"][0]["completed_orders"] == 2
    assert payload["items"][0]["total_spend"] == pytest.approx(40.0)
    assert payload["items"][0]["avg_order_value"] == pytest.approx(20.0)
    assert payload["items"][0]["avg_rating"] == pytest.approx(4.5)
    south = analytics_service.restaurant_performance(sort="name", descending=False)
    assert south["items"][1]["name"] == "South"
    assert south["items"][1]["avg_rating"] is None
    assert south["items"][1]["total_spend"] == pytest.approx(0.0)


def test_sentiment_churn_and_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _processed(tmp_path, monkeypatch)
    _write(
        directory,
        "review_sentiment.parquet",
        pd.DataFrame({"review_id": [7], "overall_sentiment": ["neutral"], "overall_score": [0.0]}),
    )
    _write(
        directory,
        "reviews.parquet",
        pd.DataFrame({"id": [7], "restaurant_id": [3], "rating": [3], "review_text": ["ok"]}),
    )
    _write(
        directory,
        "sentiment_by_restaurant.parquet",
        pd.DataFrame(
            {
                "restaurant_id": [3],
                "review_count": [1],
                "positive_count": [0],
                "negative_count": [0],
                "neutral_count": [1],
                "invalid_count": [0],
                "mean_score": [0.0],
            }
        ),
    )
    _write(directory, "restaurants.parquet", pd.DataFrame({"id": [3], "name": ["North"]}))
    report = analytics_service.sentiment_report()
    assert report["items"][0]["review_text"] == "ok"
    assert report["by_restaurant"][0]["restaurant_name"] == "North"
    _write(
        directory,
        "customer_churn_summary.parquet",
        pd.DataFrame(
            {
                "risk_category": ["high"],
                "customer_count": [1],
                "share": [1.0],
                "median_inactivity_days": [40.0],
                "median_order_frequency": [1.0],
                "median_total_spend": [10.0],
            }
        ),
    )
    _write(
        directory,
        "customer_churn_risk.parquet",
        pd.DataFrame(
            {
                "customer_id": [5, 6],
                "risk_category": ["high", "low"],
                "risk_score": [0.9, 0.1],
                "inactivity_days": [40, 1],
                "order_frequency": [1, 4],
                "total_spend": [10.0, 80.0],
                "reason_codes": ["inactive", "recent"],
            }
        ),
    )
    churn = analytics_service.churn(category="high")
    assert churn["customers"][0]["customer_id"] == 5
    assert "model-derived" in churn["notice"]
    _write(
        directory,
        "association_rules.parquet",
        pd.DataFrame(
            {
                "antecedent_names": ["Naan"],
                "consequent_names": ["Paneer"],
                "support": [0.2],
                "confidence": [0.5],
                "lift": [1.4],
                "support_count": [4],
                "restaurant_scope": ["all"],
            }
        ),
    )
    rules = analytics_service.association_rules()
    assert rules["items"][0]["antecedent_names"] == "Naan"
    assert rules["items"][0]["lift"] == pytest.approx(1.4)


def test_recommendations_and_forecast_do_not_mix_holdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _processed(tmp_path, monkeypatch)
    _write(
        directory,
        "food_recommendations.parquet",
        pd.DataFrame(
            {
                "customer_id": ["8"],
                "food_item_id": ["7"],
                "restaurant_id": ["3"],
                "recommendation_score": [0.4],
                "rank": [1],
                "reason": ["ordered together"],
            }
        ),
    )
    _write(
        directory,
        "restaurant_recommendations.parquet",
        pd.DataFrame(
            {
                "customer_id": ["8"],
                "restaurant_id": ["3"],
                "recommendation_score": [0.2],
                "rank": [1],
                "reason": ["similar cuisine"],
            }
        ),
    )
    _write(directory, "food_items.parquet", pd.DataFrame({"id": [7], "name": ["Paneer"]}))
    _write(directory, "restaurants.parquet", pd.DataFrame({"id": [3], "name": ["North"]}))
    payload = analytics_service.recommendations_for("8")
    assert payload["foods"][0]["food_name"] == "Paneer"
    assert payload["restaurants"][0]["restaurant_name"] == "North"
    history = pd.DataFrame(
        {
            "level": ["restaurant"],
            "restaurant_id": ["3"],
            "period_start": [datetime(2026, 10, 11, tzinfo=timezone.utc)],
            "actual_demand": [4.0],
            "aggregation": ["daily"],
        }
    )
    forecasts = pd.DataFrame(
        {
            "level": ["restaurant", "restaurant"],
            "restaurant_id": ["3", "3"],
            "forecast_date": [
                datetime(2026, 10, 11, tzinfo=timezone.utc),
                datetime(2026, 10, 12, tzinfo=timezone.utc),
            ],
            "predicted_demand": [9.0, 5.0],
            "aggregation": ["daily", "daily"],
            "model_name": ["ridge", "ridge"],
            "forecast_role": ["holdout", "forward"],
            "evaluation_mae": [0.2, 0.2],
            "evaluation_rmse": [0.3, 0.3],
            "evaluation_wape": [1.1, 1.1],
        }
    )
    series = analytics_service.build_forecast_series(history, forecasts, "3", "ridge", "daily")
    by_date = {point["date"]: point for point in series["points"]}
    assert by_date["2026-10-11"]["actual"] == pytest.approx(4.0)
    assert by_date["2026-10-11"]["predicted"] is None
    assert by_date["2026-10-12"]["predicted"] == pytest.approx(5.0)
    assert series["evaluation"]["mae"] == pytest.approx(0.2)


def test_invalid_sort_and_missing_file_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _processed(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    response = client.get("/analytics/association", params={"sort": "name"})
    assert response.status_code == 422
    assert "lift" in response.json()["detail"]
    missing = client.get("/analytics/segments")
    assert missing.status_code == 404
    assert "customer_segment_summary.parquet" in missing.json()["detail"]


def test_operational_average_uses_completed_orders() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Location(city="Pune", state="MH", country="India"))
    session.flush()
    session.add(Restaurant(name="North", cuisine_type="Thai", location_id=1))
    session.add(Customer(first_name="A", last_name="B", email="a@example.com"))
    session.flush()
    session.add(Order(customer_id=1, restaurant_id=1, total_amount=10, discount_used=0, status="Completed", order_date=datetime(2026, 10, 1, tzinfo=timezone.utc)))
    session.add(Order(customer_id=1, restaurant_id=1, total_amount=100, discount_used=0, status="cancelled", order_date=datetime(2026, 10, 2, tzinfo=timezone.utc)))
    session.add(Review(customer_id=1, restaurant_id=1, rating=4, review_text="good"))
    session.commit()
    stats = stats_service.get_overview_stats(session)
    assert stats.total_orders == 2
    assert stats.average_order_value == pytest.approx(10.0)
    assert stats.average_rating == pytest.approx(4.0)
    session.close()


def test_real_processed_files_have_dashboard_columns() -> None:
    root = Path(__file__).resolve().parents[2] / "data" / "processed"
    expected = {
        "orders.parquet": ["restaurant_id", "status", "total_amount"],
        "restaurants.parquet": ["id", "name", "cuisine_type"],
        "review_sentiment.parquet": ["review_id", "overall_sentiment", "overall_score"],
        "customer_segment_summary.parquet": ["segment_label", "count"],
        "customer_churn_risk.parquet": ["customer_id", "risk_score", "risk_category"],
        "association_rules.parquet": ["antecedent_names", "consequent_names", "support", "confidence", "lift"],
        "food_recommendations.parquet": ["customer_id", "food_item_id", "recommendation_score", "rank"],
        "demand_forecasts.parquet": ["restaurant_id", "forecast_date", "predicted_demand", "forecast_role", "model_name"],
        "demand_forecast_history.parquet": ["restaurant_id", "period_start", "actual_demand", "level"],
    }
    if not root.is_dir():
        pytest.skip("processed directory is not present")
    import pyarrow.parquet as pq

    for filename, columns in expected.items():
        path = root / filename
        if not path.is_file():
            pytest.skip(f"{filename} is not present")
        names = pq.read_schema(path).names
        missing = [column for column in columns if column not in names]
        assert missing == []
