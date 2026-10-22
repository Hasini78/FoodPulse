"""Read-only Parquet relationship checks. This does not write PostgreSQL or Parquet."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.validate.parquet_consistency import completed_mask, parquet_consistency_report

PROCESSED = ROOT / "data" / "processed"


def _write(directory: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(directory / name, index=False)


def test_completed_mask_lowercases_without_strip() -> None:
    orders = pd.DataFrame({"status": ["completed", "Completed", " completed", "cancelled"]})
    mask = completed_mask(orders)
    assert list(mask) == [True, True, False, False]


def test_report_finds_fk_and_recommendation_gaps(tmp_path: Path) -> None:
    stamp = pd.Timestamp("2026-01-01T00:00:00Z")
    _write(tmp_path, "locations.parquet", pd.DataFrame({"id": [1], "city": ["Pune"]}))
    _write(tmp_path, "restaurants.parquet", pd.DataFrame({"id": [10], "location_id": [1], "name": ["Thai House"]}))
    _write(
        tmp_path,
        "food_items.parquet",
        pd.DataFrame({"id": [20, 21], "restaurant_id": [10, 99], "name": ["Pad Thai", "Lost"]}),
    )
    _write(tmp_path, "customers.parquet", pd.DataFrame({"id": [1, 2]}))
    _write(
        tmp_path,
        "orders.parquet",
        pd.DataFrame(
            {
                "id": [100, 101],
                "customer_id": [1, 9],
                "restaurant_id": [10, 10],
                "status": ["completed", "cancelled"],
            }
        ),
    )
    _write(
        tmp_path,
        "order_items.parquet",
        pd.DataFrame({"id": [1, 2], "order_id": [100, 100], "food_item_id": [20, 21]}),
    )
    _write(
        tmp_path,
        "reviews.parquet",
        pd.DataFrame({"id": [7], "customer_id": [1], "restaurant_id": [10], "order_id": [100]}),
    )
    _write(
        tmp_path,
        "food_recommendations.parquet",
        pd.DataFrame({"customer_id": [1], "food_item_id": [20], "restaurant_id": [10]}),
    )
    _write(
        tmp_path,
        "restaurant_recommendations.parquet",
        pd.DataFrame({"customer_id": [1], "restaurant_id": [10]}),
    )
    report = parquet_consistency_report(tmp_path)
    gaps = report["foreign_key_gaps"]
    assert gaps["food_items_missing_restaurant"] == 1
    assert gaps["orders_missing_customer"] == 1
    assert gaps["order_items_restaurant_mismatch"] == 1
    coverage = report["recommendation_coverage"]
    assert coverage["customers_without_food_recs"] == 1
    assert coverage["customers_without_orders"] == 1
    assert report["counts"]["completed_orders"] == 1


@pytest.mark.skipif(not (PROCESSED / "order_items.parquet").is_file(), reason="processed Parquet files are not present")
def test_processed_extract_relationships_are_internally_consistent() -> None:
    report = parquet_consistency_report(PROCESSED)
    counts = report["counts"]
    assert counts["locations"] == 20
    assert counts["restaurants"] == 50
    assert counts["food_items"] == 587
    assert counts["customers"] == 500
    assert counts["orders"] == 5000
    assert counts["completed_orders"] == 4405
    assert counts["order_items"] == 14995
    assert counts["reviews"] == 3000
    assert counts["food_recommendations"] == 2500
    assert counts["restaurant_recommendations"] == 1500
    assert counts["offering_groups_with_duplicate_ids"] == 169
    assert all(value == 0 for value in report["duplicate_primary_keys"].values())
    assert all(value == 0 for value in report["foreign_key_gaps"].values())
    coverage = report["recommendation_coverage"]
    assert coverage["customers_without_food_recs"] == 0
    assert coverage["customers_without_restaurant_recs"] == 0
    assert coverage["food_recs_unknown_food"] == 0
    assert coverage["customers_without_completed_orders"] == 0
    assert coverage["food_recs_unknown_customer"] == 0
