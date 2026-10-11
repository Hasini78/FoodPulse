"""Run VADER sentiment on the processed sample reviews.

From the repository root:

    python -m mining.sentiment.run_analysis

The command reads existing Parquet files and writes new sentiment outputs.
It does not modify ``data/sample`` or the cleaned entity Parquet files, and it
does not write to PostgreSQL unless ``--persist`` is passed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from mining.sentiment.aggregate import aggregate_trends
from mining.sentiment.analyze import analyze_reviews
from mining.sentiment.evaluate import evaluate
from mining.sentiment.export import export_sentiment

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
ARTIFACTS = PROJECT_ROOT / "mining" / "sentiment" / "artifacts"


def run_analysis(processed_dir: Path = PROCESSED, artifacts_dir: Path = ARTIFACTS, persist: bool = False) -> dict:
    """Score processed reviews and write export, trends, and evaluation files."""
    reviews = pd.read_parquet(processed_dir / "reviews.parquet")
    restaurants = pd.read_parquet(processed_dir / "restaurants.parquet")
    locations = pd.read_parquet(processed_dir / "locations.parquet")
    scored = analyze_reviews(reviews)
    export_path = export_sentiment(scored, processed_dir / "review_sentiment.parquet")
    trends = aggregate_trends(scored, reviews, restaurants, locations)
    for name, frame in trends.items():
        frame.to_parquet(processed_dir / f"sentiment_{name}.parquet", index=False)
    metrics = evaluate(scored, reviews, artifacts_dir)
    if persist:
        _persist(scored)
    logger.info("Sentiment analysis wrote %s", export_path)
    return {"rows": len(scored), "metrics": metrics, "export": str(export_path)}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Score FoodPulse reviews with VADER and aspect rules")
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS)
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Upsert review_sentiment in the configured PostgreSQL database.",
    )
    args = parser.parse_args(argv)
    try:
        run_analysis(args.processed_dir, args.artifacts_dir, persist=args.persist)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _persist(scored: pd.DataFrame) -> None:
    import sys

    backend_dir = Path(__file__).resolve().parents[2] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from app.db.session import engine
    from mining.sentiment.persist import upsert_review_sentiment

    upsert_review_sentiment(scored, engine)


if __name__ == "__main__":
    sys.exit(main())
