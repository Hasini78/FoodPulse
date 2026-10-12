"""Task commands and checks for the FoodPulse Airflow DAG.

This module does not import Airflow, PySpark, Snowflake, or the ETL packages.
Importing it does not open a database connection or read ``.env``.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("foodpulse.airflow")

DEFAULT_REFERENCE_DATE = "2026-10-11"
REFERENCE_DATE_ENV = "FOODPULSE_REFERENCE_DATE"
PYTHON_ENV = "FOODPULSE_PYTHON"
SPARK_FLAG = "FOODPULSE_SPARK"
SNOWFLAKE_FLAG = "FOODPULSE_SNOWFLAKE_LOAD"
SNOWFLAKE_EXECUTE_FLAG = "FOODPULSE_SNOWFLAKE_EXECUTE"

SAMPLE_FILES = (
    "locations.csv",
    "users.csv",
    "restaurants.csv",
    "food_items.csv",
    "customers.csv",
    "orders.csv",
    "order_items.csv",
    "reviews.csv",
    "customer_activity.csv",
)

REQUIRED_OUTPUTS = (
    "validation_report.json",
    "locations.parquet",
    "users.parquet",
    "restaurants.parquet",
    "food_items.parquet",
    "customers.parquet",
    "orders.parquet",
    "order_items.parquet",
    "reviews.parquet",
    "customer_activity.parquet",
    "customer_features.parquet",
    "restaurant_features.parquet",
    "review_sentiment.parquet",
    "sentiment_by_restaurant.parquet",
    "sentiment_by_city.parquet",
    "sentiment_by_cuisine.parquet",
    "sentiment_by_month.parquet",
    "customer_segments.parquet",
    "customer_segment_summary.parquet",
    "association_frequent_itemsets.parquet",
    "association_rules.parquet",
    "customer_churn_risk.parquet",
    "customer_churn_summary.parquet",
    "food_recommendations.parquet",
    "restaurant_recommendations.parquet",
    "demand_forecasts.parquet",
    "demand_forecast_history.parquet",
)

SPARK_OUTPUTS = (
    "customer_features.parquet",
    "restaurant_features.parquet",
    "restaurant_activity.parquet",
)

# Upstream task ids. Optional tasks stay in the graph and skip at runtime.
DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "check_inputs": (),
    "etl_features": ("check_inputs",),
    "sentiment": ("etl_features",),
    "association": ("etl_features",),
    "forecasting": ("etl_features",),
    "clustering": ("sentiment",),
    "churn": ("sentiment",),
    "recommendations": ("association", "sentiment"),
    "spark_features": ("sentiment",),
    "snowflake_load": ("clustering", "churn", "recommendations", "forecasting"),
    "validate_outputs": (
        "clustering",
        "churn",
        "recommendations",
        "forecasting",
        "spark_features",
        "snowflake_load",
    ),
}


class SkipStep(Exception):
    """The task is configured off. The DAG turns this into an Airflow skip."""


def flag_enabled(name: str) -> bool:
    """True only for 1, true, or yes. Everything else, including unset, is off."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def reference_date() -> str:
    """Return the configured UTC date, or the documented sample date."""
    value = os.environ.get(REFERENCE_DATE_ENV, DEFAULT_REFERENCE_DATE).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError(f"{REFERENCE_DATE_ENV} must be YYYY-MM-DD. Received {value!r}.")
    return value


def project_root() -> Path:
    """Resolve the repository root from FOODPULSE_ROOT or this file's location."""
    override = os.environ.get("FOODPULSE_ROOT", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2]


def python_executable() -> str:
    """Use FOODPULSE_PYTHON when the Airflow worker is not the project interpreter."""
    return os.environ.get(PYTHON_ENV, "").strip() or sys.executable


def check_inputs(root: Path | None = None) -> dict[str, str]:
    """Fail when a sample CSV is missing or the reference date is not a calendar date."""
    repo = root or project_root()
    sample_dir = repo / "data" / "sample"
    missing = [name for name in SAMPLE_FILES if not (sample_dir / name).is_file()]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"Required sample files are missing from {sample_dir}: {joined}")
    chosen = reference_date()
    logger.info("Input check passed for %s using reference date %s", sample_dir, chosen)
    return {"sample_dir": str(sample_dir), "reference_date": chosen}


def etl_command(root: Path) -> list[str]:
    """Pandas transform. USE_SPARK is removed from the child environment by the runner."""
    return [
        python_executable(),
        "-m",
        "etl.pipelines.run_transform",
        "--sample-dir",
        str(root / "data" / "sample"),
        "--output-dir",
        str(root / "data" / "processed"),
        "--reference-date",
        reference_date(),
    ]


def sentiment_command(root: Path) -> list[str]:
    """Score reviews. --persist is omitted, so PostgreSQL is not written."""
    return [
        python_executable(),
        "-m",
        "mining.sentiment.run_analysis",
        "--processed-dir",
        str(root / "data" / "processed"),
        "--artifacts-dir",
        str(root / "mining" / "sentiment" / "artifacts"),
    ]


def clustering_command(root: Path) -> list[str]:
    processed = root / "data" / "processed"
    return [
        python_executable(),
        "-m",
        "mining.clustering.run_segmentation",
        "--customers",
        str(processed / "customer_features.parquet"),
        "--orders",
        str(processed / "orders.parquet"),
        "--reviews",
        str(processed / "reviews.parquet"),
        "--sentiment",
        str(processed / "review_sentiment.parquet"),
        "--output-dir",
        str(processed),
        "--artifacts-dir",
        str(root / "mining" / "clustering" / "artifacts"),
    ]


def association_command(root: Path) -> list[str]:
    processed = root / "data" / "processed"
    return [
        python_executable(),
        "-m",
        "mining.association.run_mining",
        "--orders",
        str(processed / "orders.parquet"),
        "--order-items",
        str(processed / "order_items.parquet"),
        "--food-items",
        str(processed / "food_items.parquet"),
        "--output-dir",
        str(processed),
    ]


def churn_command(root: Path) -> list[str]:
    processed = root / "data" / "processed"
    return [
        python_executable(),
        "-m",
        "mining.churn.run_analysis",
        "--customers",
        str(processed / "customer_features.parquet"),
        "--orders",
        str(processed / "orders.parquet"),
        "--reviews",
        str(processed / "reviews.parquet"),
        "--sentiment",
        str(processed / "review_sentiment.parquet"),
        "--output-dir",
        str(processed),
        "--artifacts-dir",
        str(root / "mining" / "churn" / "artifacts"),
        "--reference-date",
        reference_date(),
    ]


def recommendations_command(root: Path) -> list[str]:
    processed = root / "data" / "processed"
    return [
        python_executable(),
        "-m",
        "mining.recommendation.run_recommendations",
        "--customers",
        str(processed / "customer_features.parquet"),
        "--orders",
        str(processed / "orders.parquet"),
        "--order-items",
        str(processed / "order_items.parquet"),
        "--food-items",
        str(processed / "food_items.parquet"),
        "--restaurants",
        str(processed / "restaurants.parquet"),
        "--reviews",
        str(processed / "reviews.parquet"),
        "--sentiment",
        str(processed / "review_sentiment.parquet"),
        "--rules",
        str(processed / "association_rules.parquet"),
        "--output-dir",
        str(processed),
        "--artifacts-dir",
        str(root / "mining" / "recommendation" / "artifacts"),
        "--reference-date",
        reference_date(),
    ]


def forecasting_command(root: Path) -> list[str]:
    processed = root / "data" / "processed"
    return [
        python_executable(),
        "-m",
        "mining.forecasting.run_forecast",
        "--orders",
        str(processed / "orders.parquet"),
        "--order-items",
        str(processed / "order_items.parquet"),
        "--food-items",
        str(processed / "food_items.parquet"),
        "--output-dir",
        str(processed),
        "--artifacts-dir",
        str(root / "mining" / "forecasting" / "artifacts"),
        "--reference-date",
        reference_date(),
        "--horizon",
        "7",
        "--aggregation",
        "daily",
        "--model",
        "ridge",
    ]


def spark_command(root: Path) -> list[str]:
    """Write a separate Spark directory. This does not replace the ETL feature files."""
    return [
        python_executable(),
        str(root / "pyspark" / "jobs" / "feature_aggregations.py"),
        "--input-dir",
        str(root / "data" / "processed"),
        "--output-dir",
        str(root / "data" / "processed" / "spark_features"),
        "--reference-date",
        reference_date(),
    ]


def snowflake_command(root: Path) -> list[str]:
    """Dry-run unless FOODPULSE_SNOWFLAKE_EXECUTE is also enabled."""
    command = [
        python_executable(),
        "-m",
        "warehouse.snowflake.run_load",
        "--processed-dir",
        str(root / "data" / "processed"),
    ]
    if flag_enabled(SNOWFLAKE_EXECUTE_FLAG):
        command.append("--execute")
    else:
        command.append("--dry-run")
    return command


def run_checked(command: list[str], root: Path, *, clear_use_spark: bool = False) -> None:
    """Run a command in the repository. A non-zero exit fails the task."""
    env = os.environ.copy()
    if clear_use_spark:
        env.pop("USE_SPARK", None)
    logger.info("Running %s", " ".join(command))
    completed = subprocess.run(command, cwd=root, env=env, check=False)
    if completed.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {rendered}")


def run_etl(root: Path | None = None) -> None:
    repo = root or project_root()
    run_checked(etl_command(repo), repo, clear_use_spark=True)


def run_sentiment(root: Path | None = None) -> None:
    repo = root or project_root()
    run_checked(sentiment_command(repo), repo)


def run_clustering(root: Path | None = None) -> None:
    repo = root or project_root()
    run_checked(clustering_command(repo), repo)


def run_association(root: Path | None = None) -> None:
    repo = root or project_root()
    run_checked(association_command(repo), repo)


def run_churn(root: Path | None = None) -> None:
    repo = root or project_root()
    run_checked(churn_command(repo), repo)


def run_recommendations(root: Path | None = None) -> None:
    repo = root or project_root()
    run_checked(recommendations_command(repo), repo)


def run_forecasting(root: Path | None = None) -> None:
    repo = root or project_root()
    run_checked(forecasting_command(repo), repo)


def run_spark(root: Path | None = None) -> None:
    """Skip unless FOODPULSE_SPARK is enabled. An enabled run that fails is not swallowed."""
    if not flag_enabled(SPARK_FLAG):
        raise SkipStep("PySpark is off. Set FOODPULSE_SPARK=1 to run pyspark/jobs/feature_aggregations.py.")
    repo = root or project_root()
    run_checked(spark_command(repo), repo)


def run_snowflake(root: Path | None = None) -> None:
    """Skip unless FOODPULSE_SNOWFLAKE_LOAD is enabled. The default enabled mode is a dry-run."""
    if not flag_enabled(SNOWFLAKE_FLAG):
        raise SkipStep(
            "Snowflake load is off. Set FOODPULSE_SNOWFLAKE_LOAD=1 for a local dry-run. "
            "A live load also requires FOODPULSE_SNOWFLAKE_EXECUTE=1."
        )
    repo = root or project_root()
    run_checked(snowflake_command(repo), repo)


def validate_outputs(root: Path | None = None) -> dict[str, int]:
    """Fail if a required pipeline file is missing. Spark files are required only when Spark is on."""
    repo = root or project_root()
    processed = repo / "data" / "processed"
    missing = [name for name in REQUIRED_OUTPUTS if not (processed / name).is_file()]
    if flag_enabled(SPARK_FLAG):
        spark_dir = processed / "spark_features"
        missing.extend(
            f"spark_features/{name}" for name in SPARK_OUTPUTS if not (spark_dir / name).is_file()
        )
    if missing:
        raise FileNotFoundError("Expected output files are missing: " + ", ".join(missing))
    logger.info("Validated %s output files in %s", len(REQUIRED_OUTPUTS), processed)
    return {"validated_files": len(REQUIRED_OUTPUTS), "spark_required": int(flag_enabled(SPARK_FLAG))}
