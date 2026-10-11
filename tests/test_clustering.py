"""Tests for customer segmentation preparation, models, and artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mining.clustering.features import average_discount, prepare_model_frame, scaled_matrix
from mining.clustering.labels import label_segments
from mining.clustering.models import evaluate_clusterings
from mining.clustering.run_segmentation import run_segmentation


def _customers(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["feature_reference_date"] = "2026-10-11"
    return frame


def _orders(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _reviews(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _sentiment(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _world() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = _customers(
        [
            {"customer_id": 1, "recency_days": 5, "order_frequency": 12, "total_spend": 5000.0, "avg_order_value": 400.0, "avg_rating": 5.0},
            {"customer_id": 1, "recency_days": 99, "order_frequency": 1, "total_spend": 10.0, "avg_order_value": 10.0, "avg_rating": 1.0},
            {"customer_id": 2, "recency_days": 6, "order_frequency": 11, "total_spend": 4800.0, "avg_order_value": 420.0, "avg_rating": 4.5},
            {"customer_id": 3, "recency_days": 200, "order_frequency": 2, "total_spend": 100.0, "avg_order_value": 50.0, "avg_rating": None},
            {"customer_id": 4, "recency_days": 20, "order_frequency": 4, "total_spend": 800.0, "avg_order_value": 200.0, "avg_rating": 3.0},
            {"customer_id": 5, "recency_days": 8, "order_frequency": 10, "total_spend": 4600.0, "avg_order_value": 410.0, "avg_rating": 4.8},
            {"customer_id": 6, "recency_days": 180, "order_frequency": 2, "total_spend": 120.0, "avg_order_value": 60.0, "avg_rating": 2.0},
        ]
    )
    orders = _orders(
        [
            {"id": 1, "customer_id": 1, "discount_used": 10.0, "status": "completed", "order_date": "2026-10-01T00:00:00Z"},
            {"id": 1, "customer_id": 1, "discount_used": 999.0, "status": "completed", "order_date": "2026-10-01T00:00:00Z"},
            {"id": 2, "customer_id": 1, "discount_used": 30.0, "status": "cancelled", "order_date": "2026-10-02T00:00:00Z"},
            {"id": 3, "customer_id": 2, "discount_used": 20.0, "status": "completed", "order_date": "2026-10-03T00:00:00Z"},
            {"id": 4, "customer_id": 3, "discount_used": 5.0, "status": "pending", "order_date": "2026-09-01T00:00:00Z"},
            {"id": 5, "customer_id": 3, "discount_used": 4.0, "status": "completed", "order_date": "2026-09-02T00:00:00Z"},
            {"id": 6, "customer_id": 4, "discount_used": 0.0, "status": "completed", "order_date": "2026-09-15T00:00:00Z"},
            {"id": 7, "customer_id": 5, "discount_used": 15.0, "status": "completed", "order_date": "2026-10-05T00:00:00Z"},
            {"id": 8, "customer_id": 6, "discount_used": 2.0, "status": "completed", "order_date": "2026-08-01T00:00:00Z"},
        ]
    )
    reviews = _reviews(
        [
            {"id": 10, "customer_id": 1},
            {"id": 11, "customer_id": 2},
            {"id": 12, "customer_id": 4},
            {"id": 13, "customer_id": 5},
            {"id": 14, "customer_id": 6},
        ]
    )
    sentiment = _sentiment(
        [
            {"review_id": 10, "overall_score": 0.8},
            {"review_id": 11, "overall_score": 0.6},
            {"review_id": 12, "overall_score": 0.1},
            {"review_id": 13, "overall_score": 0.7},
            {"review_id": 14, "overall_score": -0.4},
        ]
    )
    return customers, orders, reviews, sentiment


def test_discount_ignores_duplicates_and_non_completed_orders() -> None:
    _, orders, _, _ = _world()
    discounts = average_discount(orders, datetime(2026, 10, 11, tzinfo=timezone.utc).date())
    customer_one = discounts.loc[discounts["customer_id"] == 1, "avg_discount"].item()
    assert customer_one == 10.0
    assert 3 in set(discounts["customer_id"])


def test_preparation_drops_duplicate_customers_and_scales() -> None:
    customers, orders, reviews, sentiment = _world()
    frame, scaler, notes = prepare_model_frame(customers, orders, reviews, sentiment)
    assert frame["customer_id"].tolist() == [1, 2, 3, 4, 5, 6]
    assert notes["duplicate_customers_removed"] == 1
    assert "avg_rating" in notes["imputed_counts"]
    assert "avg_sentiment_score" in notes["imputed_counts"]
    assert "customer_id" not in scaler.feature_names_in_
    scaled = scaled_matrix(frame, scaler)
    assert scaled.shape == (6, 7)
    assert np.allclose(scaled.mean().to_numpy(), 0, atol=1e-6)


def test_missing_column_raises() -> None:
    customers, orders, reviews, sentiment = _world()
    broken = customers.drop(columns=["total_spend"])
    with pytest.raises(ValueError, match="total_spend"):
        prepare_model_frame(broken, orders, reviews, sentiment)


def test_small_dataset_does_not_crash() -> None:
    matrix = pd.DataFrame({"recency_days": [1.0, 2.0], "order_frequency": [1.0, 2.0]})
    selected, runs = evaluate_clusterings(matrix, seed=1)
    assert selected.algorithm == "none"
    assert selected.eligible is False
    assert len(runs) == 1


def test_clustering_is_reproducible_and_rejects_invalid_shape() -> None:
    rng = np.random.default_rng(0)
    first = np.repeat([[0.0, 0.0], [5.0, 5.0], [10.0, 0.0]], 8, axis=0)
    noise = rng.normal(0, 0.05, size=first.shape)
    values = pd.DataFrame(first + noise, columns=["recency_days", "order_frequency"])
    selected_a, _ = evaluate_clusterings(values, seed=7)
    selected_b, _ = evaluate_clusterings(values, seed=7)
    assert selected_a.algorithm == selected_b.algorithm
    assert np.array_equal(selected_a.labels, selected_b.labels)
    assert selected_a.metrics["silhouette"] is not None
    assert selected_a.metrics["davies_bouldin"] is not None
    assert selected_a.metrics["calinski_harabasz"] is not None


def test_summary_names_segments_from_measurements() -> None:
    frame = pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 4],
            "recency_days": [5, 6, 200, 180],
            "order_frequency": [12, 11, 2, 2],
            "total_spend": [5000.0, 4800.0, 100.0, 120.0],
            "avg_order_value": [400.0, 420.0, 50.0, 60.0],
            "avg_discount": [10.0, 12.0, 1.0, 1.0],
            "avg_rating": [5.0, 4.5, 2.0, 2.0],
            "avg_sentiment_score": [0.8, 0.7, -0.2, -0.3],
        }
    )
    labels = pd.Series([0, 0, 1, 1])
    assigned, summary = label_segments(frame, labels)
    assert set(assigned["segment_label"]) == {"high-value loyal", "inactive/at-risk"}
    assert summary["count"].sum() == 4
    assert set(summary["segment_label"]) == {"high-value loyal", "inactive/at-risk"}


def test_run_writes_artifacts_without_touching_inputs(tmp_path: Path) -> None:
    customers, orders, reviews, sentiment = _world()
    source = tmp_path / "in"
    output = tmp_path / "out"
    artifacts = tmp_path / "artifacts"
    source.mkdir()
    customers.to_parquet(source / "customers.parquet", index=False)
    orders.to_parquet(source / "orders.parquet", index=False)
    reviews.to_parquet(source / "reviews.parquet", index=False)
    sentiment.to_parquet(source / "sentiment.parquet", index=False)
    before = (source / "customers.parquet").read_bytes()
    payload = run_segmentation(
        source / "customers.parquet",
        source / "orders.parquet",
        source / "reviews.parquet",
        source / "sentiment.parquet",
        output,
        artifacts,
        seed=42,
    )
    assert (source / "customers.parquet").read_bytes() == before
    assert (output / "customer_segments.parquet").is_file()
    assert (output / "customer_segment_summary.parquet").is_file()
    assert (output / "customer_segmentation_metrics.json").is_file()
    assert (artifacts / "customer_segments_pca.png").is_file()
    segments = pd.read_parquet(output / "customer_segments.parquet")
    assert segments["customer_id"].nunique() == len(segments) == 6
    assert payload["selected_algorithm"] in {"kmeans", "agglomerative", "dbscan", "none"}


def test_missing_input_file_returns_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        run_segmentation(
            tmp_path / "missing.parquet",
            tmp_path / "orders.parquet",
            tmp_path / "reviews.parquet",
            tmp_path / "sentiment.parquet",
            tmp_path,
            tmp_path,
            seed=1,
        )
