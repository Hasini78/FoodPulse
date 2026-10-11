"""Compare VADER labels with rating-derived proxy labels.

Ratings are a weak proxy, not human sentiment annotation:

- 1 and 2 → negative
- 3 → neutral
- 4 and 5 → positive

Missing ratings are excluded. Classes with no support contribute zero precision
and recall instead of raising a division error.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger(__name__)

LABELS = ("negative", "neutral", "positive")
PROXY_NOTE = (
    "Rating proxy labels are weak supervision, not human aspect or sentiment annotation. "
    "1-2 map to negative, 3 to neutral, and 4-5 to positive."
)


def rating_proxy(rating: object) -> str | None:
    """Map a star rating to a proxy label. Missing or out-of-range ratings return None."""
    if rating is None or (isinstance(rating, float) and pd.isna(rating)):
        return None
    try:
        if pd.isna(rating):
            return None
    except TypeError:
        pass
    try:
        value = int(rating)
    except (TypeError, ValueError):
        return None
    if value in (1, 2):
        return "negative"
    if value == 3:
        return "neutral"
    if value in (4, 5):
        return "positive"
    return None


def evaluate(
    scored: pd.DataFrame,
    reviews: pd.DataFrame,
    output_dir: Path,
) -> dict[str, object]:
    """Write metrics JSON and a confusion-matrix image. Return the metrics payload."""
    output_dir.mkdir(parents=True, exist_ok=True)
    merged = scored.merge(
        reviews.loc[:, ["id", "rating"]].drop_duplicates(subset=["id"]),
        left_on="review_id",
        right_on="id",
        how="left",
    )
    merged["proxy"] = merged["rating"].map(rating_proxy)
    usable = merged.loc[merged["proxy"].notna() & merged["overall_sentiment"].isin(LABELS)].copy()
    skipped = int(len(merged) - len(usable))
    matrix = _confusion(usable["proxy"].tolist(), usable["overall_sentiment"].tolist())
    metrics = _metrics(matrix)
    image_path = output_dir / "confusion_matrix.png"
    _save_matrix(matrix, image_path)
    payload: dict[str, object] = {
        "note": PROXY_NOTE,
        "rows_scored": int(len(scored)),
        "rows_evaluated": int(len(usable)),
        "rows_skipped_missing_or_invalid_rating": skipped,
        "accuracy": metrics["accuracy"],
        "precision_macro": metrics["precision_macro"],
        "recall_macro": metrics["recall_macro"],
        "f1_macro": metrics["f1_macro"],
        "per_class": metrics["per_class"],
        "confusion_matrix": {
            "labels": list(LABELS),
            "rows_are": "proxy_rating",
            "columns_are": "predicted_sentiment",
            "values": matrix,
        },
        "confusion_matrix_image": str(image_path),
    }
    report_path = output_dir / "evaluation.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(
        "Sentiment evaluation accuracy=%.3f on %s rows (%s skipped)",
        metrics["accuracy"],
        len(usable),
        skipped,
    )
    return payload


def _confusion(truth: list[str], predicted: list[str]) -> list[list[int]]:
    index = {label: position for position, label in enumerate(LABELS)}
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for actual, guess in zip(truth, predicted, strict=True):
        matrix[index[actual]][index[guess]] += 1
    return matrix


def _metrics(matrix: list[list[int]]) -> dict[str, object]:
    total = sum(sum(row) for row in matrix)
    correct = sum(matrix[i][i] for i in range(len(LABELS)))
    per_class: dict[str, dict[str, float]] = {}
    precisions: list[float] = []
    recalls: list[float] = []
    f1_scores: list[float] = []
    for position, label in enumerate(LABELS):
        tp = matrix[position][position]
        predicted_count = sum(matrix[row][position] for row in range(len(LABELS)))
        actual_count = sum(matrix[position])
        precision = tp / predicted_count if predicted_count else 0.0
        recall = tp / actual_count if actual_count else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": actual_count,
        }
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)
    return {
        "accuracy": (correct / total) if total else 0.0,
        "precision_macro": sum(precisions) / len(LABELS),
        "recall_macro": sum(recalls) / len(LABELS),
        "f1_macro": sum(f1_scores) / len(LABELS),
        "per_class": per_class,
    }


def _save_matrix(matrix: list[list[int]], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(5, 4))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(LABELS)), list(LABELS))
    axis.set_yticks(range(len(LABELS)), list(LABELS))
    axis.set_xlabel("Predicted sentiment")
    axis.set_ylabel("Rating proxy")
    axis.set_title("Sentiment confusion matrix")
    for row in range(len(LABELS)):
        for column in range(len(LABELS)):
            axis.text(column, row, str(matrix[row][column]), ha="center", va="center")
    figure.colorbar(image, ax=axis, fraction=0.046)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    logger.info("Wrote confusion matrix to %s", path)
