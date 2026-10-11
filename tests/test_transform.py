"""Tests for cleaning, validation, features, and the transform pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from etl.pipelines.run_transform import run_pipeline
from etl.transform.cleaning import (
    clean_dataset,
    dedupe_by_primary_key,
    flag_order_total_outliers,
    normalize_review_text,
)
from etl.transform.feature_engineering import build_customer_features, build_restaurant_features
from etl.transform.validation import (
    CriticalValidationError,
    assert_no_critical_errors,
    validate_all,
    validate_dataset,
)

REFERENCE = date(2026, 10, 11)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dedupe_keeps_distinct_ids_and_first_duplicate() -> None:
    frame = pd.DataFrame(
        [
            {"id": 1, "name": "A"},
            {"id": 1, "name": "B"},
            {"id": 2, "name": "A"},
        ]
    )
    original = frame.copy()
    cleaned = dedupe_by_primary_key(frame, "id")
    pd.testing.assert_frame_equal(frame, original)
    assert cleaned["id"].tolist() == [1, 2]
    assert cleaned.loc[cleaned["id"] == 1, "name"].item() == "A"


def test_missing_identifier_is_not_invented() -> None:
    frame = pd.DataFrame(
        [
            {
                "id": None,
                "customer_id": 1,
                "restaurant_id": 1,
                "total_amount": 10,
                "discount_used": None,
                "status": "completed",
                "order_date": "2026-10-01T00:00:00Z",
                "created_at": "2026-10-01T00:00:00Z",
            }
        ]
    )
    cleaned = clean_dataset(frame, "orders")
    assert pd.isna(cleaned.loc[0, "id"])
    assert cleaned.loc[0, "discount_used"] == 0


def test_microsecond_timestamps_are_parsed() -> None:
    frame = pd.DataFrame(
        [
            {
                "id": 1,
                "customer_id": 1,
                "restaurant_id": 1,
                "order_id": 1,
                "rating": 4,
                "review_text": "Not good",
                "created_at": "2026-10-07 06:13:42.018369+00:00",
            }
        ]
    )
    cleaned = clean_dataset(frame, "reviews")
    assert cleaned.loc[0, "created_at"] == pd.Timestamp("2026-10-07 06:13:42.018369", tz="UTC")


def test_type_conversion_and_boolean_text() -> None:
    frame = pd.DataFrame(
        [
            {
                "id": "1",
                "name": "  Spice House  ",
                "cuisine_type": "Indian",
                "description": "",
                "phone": " 555 ",
                "email": "a@b.c",
                "location_id": "1",
                "is_active": "True",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]
    )
    cleaned = clean_dataset(frame, "restaurants")
    assert cleaned.loc[0, "id"] == 1
    assert cleaned.loc[0, "name"] == "Spice House"
    assert pd.isna(cleaned.loc[0, "description"])
    assert bool(cleaned.loc[0, "is_active"]) is True
    assert cleaned.loc[0, "created_at"].tzinfo is not None


def test_review_text_preserves_negation_contrast_and_punctuation() -> None:
    assert normalize_review_text("  <b>Not good</b> ") == "not good"
    assert normalize_review_text(" Slow! ") == "slow!"
    assert normalize_review_text("Amazing but expensive") == "amazing but expensive"
    assert normalize_review_text("Good &amp; hot") == "good & hot"
    frame = pd.DataFrame(
        [
            {
                "id": 1,
                "customer_id": 1,
                "restaurant_id": 1,
                "order_id": 1,
                "rating": 2,
                "review_text": "<p>Not good</p> but slow!",
                "created_at": "2026-10-02T00:00:00Z",
            }
        ]
    )
    original_text = frame.loc[0, "review_text"]
    cleaned = clean_dataset(frame, "reviews")
    assert frame.loc[0, "review_text"] == original_text
    assert cleaned.loc[0, "review_text"] == "not good but slow!"


def test_outlier_keeps_original_total() -> None:
    frame = pd.DataFrame({"id": range(1, 7), "total_amount": [10, 10, 10, 10, 10, 1000]})
    flagged = flag_order_total_outliers(frame)
    assert frame["total_amount"].tolist()[-1] == 1000
    outlier = flagged.loc[flagged["id"] == 6].iloc[0]
    assert bool(outlier["is_total_outlier"]) is True
    assert outlier["total_amount"] == 1000
    assert outlier["total_amount_capped"] == outlier["outlier_upper_fence"]
    assert outlier["outlier_method"].startswith("tukey_iqr_1.5")


def _world() -> dict[str, pd.DataFrame]:
    created = "2026-01-01T00:00:00Z"
    return {
        "locations": pd.DataFrame(
            [
                {
                    "id": 1,
                    "city": "Pune",
                    "state": "MH",
                    "country": "India",
                    "postal_code": "411001",
                    "latitude": 18.5,
                    "longitude": 73.8,
                    "created_at": created,
                }
            ]
        ),
        "users": pd.DataFrame(
            [
                {
                    "id": 1,
                    "email": "analyst@foodpulse.local",
                    "full_name": "A Analyst",
                    "hashed_password": "abc",
                    "is_active": True,
                    "role": "analyst",
                    "created_at": created,
                }
            ]
        ),
        "restaurants": pd.DataFrame(
            [
                {
                    "id": 1,
                    "name": "Spice House",
                    "cuisine_type": "Indian",
                    "description": "North Indian",
                    "phone": "555",
                    "email": "spice@example.com",
                    "location_id": 1,
                    "is_active": True,
                    "created_at": created,
                }
            ]
        ),
        "food_items": pd.DataFrame(
            [
                {
                    "id": 1,
                    "restaurant_id": 1,
                    "name": "Naan",
                    "category": "Bread",
                    "description": "Bread",
                    "price": 40.0,
                    "is_available": True,
                    "created_at": created,
                }
            ]
        ),
        "customers": pd.DataFrame(
            [
                {
                    "id": 1,
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "email": "ada@example.com",
                    "phone": "1",
                    "city": "Pune",
                    "date_of_birth": "1990-01-01",
                    "gender": "female",
                    "created_at": created,
                },
                {
                    "id": 2,
                    "first_name": "Grace",
                    "last_name": "Hopper",
                    "email": "grace@example.com",
                    "phone": "2",
                    "city": "Pune",
                    "date_of_birth": "1991-01-01",
                    "gender": None,
                    "created_at": created,
                },
            ]
        ),
        "orders": pd.DataFrame(
            [
                {
                    "id": 1,
                    "customer_id": 1,
                    "restaurant_id": 1,
                    "total_amount": 100.0,
                    "discount_used": 10.0,
                    "status": "completed",
                    "order_date": "2026-10-01T00:00:00Z",
                    "created_at": "2026-10-01T00:00:00Z",
                },
                {
                    "id": 2,
                    "customer_id": 1,
                    "restaurant_id": 1,
                    "total_amount": 50.0,
                    "discount_used": 0.0,
                    "status": "completed",
                    "order_date": "2026-10-05T12:00:00Z",
                    "created_at": "2026-10-05T12:00:00Z",
                },
                {
                    "id": 3,
                    "customer_id": 1,
                    "restaurant_id": 1,
                    "total_amount": 999.0,
                    "discount_used": 0.0,
                    "status": "cancelled",
                    "order_date": "2026-10-06T00:00:00Z",
                    "created_at": "2026-10-06T00:00:00Z",
                },
            ]
        ),
        "order_items": pd.DataFrame(
            [
                {"id": 1, "order_id": 1, "food_item_id": 1, "quantity": 1, "unit_price": 40.0, "subtotal": 40.0},
                {"id": 2, "order_id": 1, "food_item_id": 1, "quantity": 2, "unit_price": 40.0, "subtotal": 80.0},
            ]
        ),
        "reviews": pd.DataFrame(
            [
                {
                    "id": 1,
                    "customer_id": 1,
                    "restaurant_id": 1,
                    "order_id": 1,
                    "rating": 5,
                    "review_text": "Amazing but expensive",
                    "created_at": "2026-10-02T00:00:00Z",
                },
                {
                    "id": 2,
                    "customer_id": 1,
                    "restaurant_id": 1,
                    "order_id": 2,
                    "rating": 1,
                    "review_text": "Not good",
                    "created_at": "2026-10-06T00:00:00Z",
                },
            ]
        ),
        "customer_activity": pd.DataFrame(
            [
                {
                    "id": 1,
                    "customer_id": 1,
                    "activity_type": "place_order",
                    "description": "ordered",
                    "activity_date": "2026-10-01T00:00:00Z",
                    "created_at": "2026-10-01T00:00:00Z",
                }
            ]
        ),
    }


def _cleaned_world() -> dict[str, pd.DataFrame]:
    raw = _world()
    return {name: clean_dataset(frame, name) for name, frame in raw.items()}


def test_validation_passes_with_optional_gender_warning() -> None:
    frames = _cleaned_world()
    report = validate_all(frames, reference_date=REFERENCE)
    assert report["status"] == "warning"
    customer_report = next(item for item in report["datasets"] if item["dataset"] == "customers")
    assert customer_report["status"] == "warning"
    assert any(item["check"] == "optional_missing" for item in customer_report["warnings"])
    assert customer_report["critical_errors"] == []
    assert_no_critical_errors(report)


def test_validation_fails_on_duplicate_key_bad_rating_and_dangling_fk() -> None:
    frames = _cleaned_world()
    orders = frames["orders"].copy()
    orders.loc[0, "customer_id"] = 999
    broken_orders = validate_dataset(orders, "orders", frames, reference_date=REFERENCE)
    assert broken_orders["status"] == "failed"
    assert any(item["check"] == "referential_integrity" for item in broken_orders["critical_errors"])

    reviews = frames["reviews"].copy()
    reviews.loc[0, "rating"] = 9
    broken_reviews = validate_dataset(reviews, "reviews", frames, reference_date=REFERENCE)
    assert any(item["check"] == "rating_range" for item in broken_reviews["critical_errors"])

    duplicated = pd.concat([frames["customers"], frames["customers"].head(1)], ignore_index=True)
    broken_customers = validate_dataset(duplicated, "customers", frames, reference_date=REFERENCE)
    assert any(item["check"] == "primary_key_unique" for item in broken_customers["critical_errors"])


def test_negative_amount_and_absurd_date_are_critical_future_date_warns() -> None:
    frames = _cleaned_world()
    items = frames["food_items"].copy()
    items.loc[0, "price"] = -1
    price_report = validate_dataset(items, "food_items", frames, reference_date=REFERENCE)
    assert any(item["check"] == "non_negative_amounts" for item in price_report["critical_errors"])

    orders = frames["orders"].copy()
    orders.loc[0, "order_date"] = pd.Timestamp("1890-01-01", tz="UTC")
    old_report = validate_dataset(orders, "orders", frames, reference_date=REFERENCE)
    assert any(item["check"] == "sensible_dates" for item in old_report["critical_errors"])

    future = frames["orders"].copy()
    future.loc[0, "order_date"] = pd.Timestamp("2026-10-12", tz="UTC")
    future_report = validate_dataset(future, "orders", frames, reference_date=REFERENCE)
    assert future_report["status"] == "warning"
    assert any(item["check"] == "dates_after_reference" for item in future_report["warnings"])
    assert_no_critical_errors({"status": "warning", "datasets": [future_report]})


def test_customer_features_are_reproducible_and_ignore_cancelled_orders() -> None:
    frames = _cleaned_world()
    first = build_customer_features(
        frames["customers"], frames["orders"], frames["reviews"], reference_date=REFERENCE
    )
    second = build_customer_features(
        frames["customers"], frames["orders"], frames["reviews"], reference_date=REFERENCE
    )
    pd.testing.assert_frame_equal(first, second)
    ada = first.loc[first["customer_id"] == 1].iloc[0]
    grace = first.loc[first["customer_id"] == 2].iloc[0]
    assert ada["recency_days"] == 6
    assert ada["order_frequency"] == 2
    assert ada["total_spend"] == 150
    assert ada["avg_order_value"] == 75
    assert ada["avg_rating"] == 3
    assert ada["review_frequency"] == 2
    assert ada["discount_usage_rate"] == 0.5
    assert grace["order_frequency"] == 0
    assert grace["total_spend"] == 0
    assert pd.isna(grace["recency_days"])
    assert pd.isna(grace["discount_usage_rate"])
    assert len(first) == 2


def test_restaurant_features_and_complaint_heuristic() -> None:
    frames = _cleaned_world()
    features = build_restaurant_features(
        frames["restaurants"], frames["orders"], frames["reviews"], reference_date=REFERENCE
    )
    row = features.iloc[0]
    assert row["restaurant_id"] == 1
    assert row["avg_rating"] == 3
    assert row["rolling_avg_rating"] == 3
    assert row["review_volume"] == 2
    assert row["order_volume"] == 2
    assert row["complaint_count"] == 1
    assert pd.isna(row["sentiment_label"])
    assert pd.isna(row["sentiment_score"])


def test_order_items_do_not_duplicate_spend() -> None:
    frames = _cleaned_world()
    features = build_customer_features(
        frames["customers"], frames["orders"], frames["reviews"], reference_date=REFERENCE
    )
    spend = features.loc[features["customer_id"] == 1, "total_spend"].item()
    joined = frames["orders"].merge(frames["order_items"], left_on="id", right_on="order_id")
    duplicated_spend = joined.loc[joined["status"] == "completed", "total_amount"].sum()
    assert spend == 150
    assert duplicated_spend > spend


def _write_csv_world(directory: Path, frames: dict[str, pd.DataFrame]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_csv(directory / f"{name}.csv", index=False)


def test_pipeline_writes_parquet_and_stops_on_critical_errors(tmp_path: Path) -> None:
    sample = tmp_path / "sample"
    output = tmp_path / "processed"
    _write_csv_world(sample, _world())
    report = run_pipeline(sample, output, reference_date="2026-10-11")
    assert report["status"] == "warning"
    assert (output / "validation_report.json").is_file()
    customers = pd.read_parquet(output / "customer_features.parquet")
    restaurants = pd.read_parquet(output / "restaurant_features.parquet")
    assert customers["customer_id"].tolist() == [1, 2]
    assert restaurants["restaurant_id"].tolist() == [1]
    stored = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))
    assert stored["status"] == "warning"

    broken = _world()
    broken["orders"].loc[0, "customer_id"] = 999
    broken_dir = tmp_path / "broken"
    broken_out = tmp_path / "broken_out"
    _write_csv_world(broken_dir, broken)
    with pytest.raises(CriticalValidationError, match="critical errors"):
        run_pipeline(broken_dir, broken_out, reference_date="2026-10-11")
    assert (broken_out / "validation_report.json").is_file()
    assert not (broken_out / "customer_features.parquet").exists()


def test_sample_pipeline_does_not_change_source_csvs(tmp_path: Path) -> None:
    before = {path.name: _sha256(path) for path in SAMPLE_DIR.glob("*.csv")}
    output = tmp_path / "processed"
    report = run_pipeline(SAMPLE_DIR, output, reference_date="2026-10-11")
    after = {path.name: _sha256(path) for path in SAMPLE_DIR.glob("*.csv")}
    assert before == after
    assert report["status"] in {"passed", "warning"}
    assert (output / "orders.parquet").is_file()
    assert (output / "reviews.parquet").is_file()
    features = pd.read_parquet(output / "customer_features.parquet")
    assert features["customer_id"].nunique() == len(features)
    assert len(features) == 500
