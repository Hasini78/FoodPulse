"""Run customer segmentation.

From the repository root:

    python -m mining.clustering.run_segmentation
    python -m mining.clustering.run_segmentation --seed 42

The command reads processed Parquet files and writes new segment outputs.
It does not modify the source files or connect to a database.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.decomposition import PCA

from mining.clustering.features import prepare_model_frame, scaled_matrix
from mining.clustering.labels import LABEL_RULES, label_segments
from mining.clustering.models import evaluate_clusterings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
ARTIFACTS = PROJECT_ROOT / "mining" / "clustering" / "artifacts"


def run_segmentation(
    customer_path: Path,
    orders_path: Path,
    reviews_path: Path,
    sentiment_path: Path,
    output_dir: Path,
    artifacts_dir: Path,
    seed: int,
) -> dict[str, object]:
    """Prepare features, select a clustering model, and write artifacts."""
    for path in (customer_path, orders_path, reviews_path, sentiment_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
    customers = pd.read_parquet(customer_path)
    orders = pd.read_parquet(orders_path)
    reviews = pd.read_parquet(reviews_path)
    sentiment = pd.read_parquet(sentiment_path)
    frame, scaler, notes = prepare_model_frame(customers, orders, reviews, sentiment)
    matrix = scaled_matrix(frame, scaler)
    selected, runs = evaluate_clusterings(matrix, seed)
    labels = pd.Series(selected.labels, index=frame.index)
    assigned, summary = label_segments(frame, labels)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    segments = assigned.loc[:, ["customer_id", "cluster_id", "segment_label"]].sort_values("customer_id")
    segment_path = output_dir / "customer_segments.parquet"
    summary_path = output_dir / "customer_segment_summary.parquet"
    metrics_path = output_dir / "customer_segmentation_metrics.json"
    plot_path = artifacts_dir / "customer_segments_pca.png"
    segments.to_parquet(segment_path, index=False)
    summary.to_parquet(summary_path, index=False)
    _plot(matrix, assigned["segment_label"], plot_path)
    payload = {
        "dataset": {
            "customer_count": notes["customer_count"],
            "feature_reference_date": notes["feature_reference_date"],
            "duplicate_customers_removed": notes["duplicate_customers_removed"],
            "input_customer_features": str(customer_path),
        },
        "features": notes["features"],
        "feature_reasons": notes["feature_reasons"],
        "imputed_counts": notes["imputed_counts"],
        "clip_bounds": notes["clip_bounds"],
        "scaler": notes["scaler"],
        "seed": seed,
        "selected_algorithm": selected.algorithm,
        "selected_params": selected.params,
        "selected_metrics": selected.metrics,
        "selection_note": selected.note,
        "selection_rule": (
            "Highest silhouette among eligible models. If another model is within 0.01 "
            "silhouette, prefer K-Means, then agglomerative clustering, then fewer clusters."
        ),
        "label_rules": list(LABEL_RULES),
        "label_note": "Segment names are descriptive comparisons with the population medians, not statistically validated categories.",
        "candidates": [
            {
                "algorithm": run.algorithm,
                "params": run.params,
                "metrics": run.metrics,
                "eligible": run.eligible,
                "note": run.note,
            }
            for run in runs
        ],
        "artifacts": {
            "segments": str(segment_path),
            "summary": str(summary_path),
            "metrics": str(metrics_path),
            "pca_plot": str(plot_path),
        },
    }
    metrics_path.write_text(json.dumps(_json_ready(payload), indent=2), encoding="utf-8")
    logger.info("Wrote customer segments for %s customers to %s", len(segments), segment_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Cluster FoodPulse customers from processed features")
    parser.add_argument("--customers", type=Path, default=PROCESSED / "customer_features.parquet")
    parser.add_argument("--orders", type=Path, default=PROCESSED / "orders.parquet")
    parser.add_argument("--reviews", type=Path, default=PROCESSED / "reviews.parquet")
    parser.add_argument("--sentiment", type=Path, default=PROCESSED / "review_sentiment.parquet")
    parser.add_argument("--output-dir", type=Path, default=PROCESSED)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        run_segmentation(
            args.customers,
            args.orders,
            args.reviews,
            args.sentiment,
            args.output_dir,
            args.artifacts_dir,
            args.seed,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _json_ready(value):
    """Convert NumPy values so the metrics file is valid JSON."""
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, str):
        return value
    return value


def _plot(matrix: pd.DataFrame, labels: pd.Series, path: Path) -> None:
    components = PCA(n_components=2, random_state=0).fit_transform(matrix)
    figure, axis = plt.subplots(figsize=(8, 5))
    for label in sorted(labels.unique()):
        mask = labels.to_numpy() == label
        axis.scatter(components[mask, 0], components[mask, 1], s=18, label=label)
    axis.set_xlabel("PC1 (visualization only)")
    axis.set_ylabel("PC2 (visualization only)")
    axis.set_title("Customer segments")
    axis.legend(title="Segment", fontsize=8)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    logger.info("Wrote PCA cluster plot to %s", path)


if __name__ == "__main__":
    sys.exit(main())
