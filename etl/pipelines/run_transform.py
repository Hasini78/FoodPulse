"""Transform pipeline: sample CSVs to cleaned Parquet and feature tables.

Run from the repository root:

    python -m etl.pipelines.run_transform
    python -m etl.pipelines.run_transform --reference-date 2026-10-11

The pipeline reads ``data/sample``, cleans each table, writes
``data/processed/validation_report.json``, and stops when that report
contains critical errors. Otherwise it writes cleaned Parquet tables and
``customer_features.parquet`` / ``restaurant_features.parquet``.

Source CSVs are only read. Set ``USE_SPARK=1`` to aggregate features with
``pyspark/jobs/feature_aggregations.py``. The default path is Pandas and does
not import PySpark.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from etl.transform.cleaning import clean_dataset
from etl.transform.dataset_specs import DATASET_ORDER
from etl.transform.feature_engineering import (
    build_customer_features,
    build_restaurant_features,
    parse_reference_date,
)
from etl.transform.validation import assert_no_critical_errors, validate_all, write_report

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
SPARK_JOB = PROJECT_ROOT / "pyspark" / "jobs" / "feature_aggregations.py"


def run_pipeline(
    sample_dir: Path = DEFAULT_SAMPLE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    reference_date: str | None = None,
) -> dict:
    """Clean, validate, and write features. Raise on critical validation errors."""
    resolved_date = parse_reference_date(reference_date or os.getenv("FEATURE_REFERENCE_DATE"))
    raw_frames = read_sample_csvs(sample_dir)
    cleaned = {name: clean_dataset(frame, name) for name, frame in raw_frames.items()}
    report = validate_all(cleaned, reference_date=resolved_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_report(report, output_dir / "validation_report.json")
    assert_no_critical_errors(report)

    for name, frame in cleaned.items():
        _write_parquet(frame, output_dir / f"{name}.parquet")

    if _use_spark():
        customer_features, restaurant_features = _spark_features(cleaned, resolved_date)
    else:
        customer_features = build_customer_features(
            cleaned["customers"],
            cleaned["orders"],
            cleaned["reviews"],
            reference_date=resolved_date,
        )
        restaurant_features = build_restaurant_features(
            cleaned["restaurants"],
            cleaned["orders"],
            cleaned["reviews"],
            reference_date=resolved_date,
        )
    _write_parquet(customer_features, output_dir / "customer_features.parquet")
    _write_parquet(restaurant_features, output_dir / "restaurant_features.parquet")
    logger.info("Transform pipeline finished with status=%s", report["status"])
    return report


def read_sample_csvs(sample_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the nine sample tables. The files are not opened for writing."""
    frames: dict[str, pd.DataFrame] = {}
    for name in DATASET_ORDER:
        path = sample_dir / f"{name}.csv"
        frames[name] = pd.read_csv(path)
        logger.info("Read %s (%s rows)", path, len(frames[name]))
    return frames


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success and 1 on critical validation errors."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Clean, validate, and featurize FoodPulse sample CSVs")
    parser.add_argument("--sample-dir", type=Path, default=DEFAULT_SAMPLE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--reference-date",
        default=None,
        help="UTC reference date (YYYY-MM-DD) for recency and rolling ratings. Defaults to today.",
    )
    args = parser.parse_args(argv)
    try:
        run_pipeline(args.sample_dir, args.output_dir, args.reference_date)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    try:
        frame.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Writing Parquet requires pyarrow. It is listed in requirements.txt; "
            "install it into the active environment."
        ) from exc
    logger.info("Wrote %s", path)


def _use_spark() -> bool:
    return os.getenv("USE_SPARK", "").strip().lower() in {"1", "true", "yes"}


def _spark_features(cleaned: dict[str, pd.DataFrame], reference_date):
    spec = importlib.util.spec_from_file_location("foodpulse_spark_features", SPARK_JOB)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Spark feature job at {SPARK_JOB}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_features(
        cleaned["customers"],
        cleaned["restaurants"],
        cleaned["orders"],
        cleaned["reviews"],
        reference_date=reference_date,
    )


if __name__ == "__main__":
    sys.exit(main())
