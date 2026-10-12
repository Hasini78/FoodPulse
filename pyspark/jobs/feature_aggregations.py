"""Spark aggregations that follow the Pandas feature definitions.

Run from the repository root. This writes a new directory and does not replace
the Parquet files produced by ``etl.pipelines.run_transform``:

    .\\.venv\\Scripts\\python.exe pyspark\\jobs\\feature_aggregations.py --reference-date 2026-10-11

The folder ``pyspark/`` in this repository is the project job directory. It is
not the PySpark library. The job loads the installed library from
site-packages so the two names do not collide.

``sentiment_label`` and ``sentiment_score`` stay null, matching
``etl.transform.feature_engineering``. When ``review_sentiment.parquet`` is
present, restaurant sentiment counts are written as a separate file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.transform.feature_engineering import (
    COMPLAINT_RATING_MAX,
    COMPLETED_ORDER_STATUS,
    CUSTOMER_FEATURE_COLUMNS,
    RESTAURANT_FEATURE_COLUMNS,
    ROLLING_RATING_WINDOW_DAYS,
    end_of_reference_day,
    parse_reference_date,
)

logger = logging.getLogger(__name__)

DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "spark_features"

REQUIRED_FILES = {
    "customers": ("id",),
    "restaurants": ("id",),
    "orders": ("id", "customer_id", "restaurant_id", "total_amount", "discount_used", "status", "order_date"),
    "reviews": ("id", "customer_id", "restaurant_id", "rating", "created_at"),
}
SENTIMENT_FILE = "review_sentiment"
SENTIMENT_COLUMNS = ("review_id", "overall_sentiment", "overall_score")
SENTIMENT_LABELS = ("positive", "negative", "neutral", "invalid")


def build_features(
    customers: pd.DataFrame,
    restaurants: pd.DataFrame,
    orders: pd.DataFrame,
    reviews: pd.DataFrame,
    *,
    reference_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate the in-memory frames. Used by ``USE_SPARK=1`` in the ETL pipeline.

    The pipeline already holds the cleaned tables. This function does not read
    or write ``data/processed``.
    """
    spark = _session()
    spark_types = _spark_modules()[2]
    try:
        customer_features, restaurant_features, _activity, _sentiment = _aggregate(
            spark,
            _frame(spark, spark_types, customers, "customers"),
            _frame(spark, spark_types, restaurants, "restaurants"),
            _frame(spark, spark_types, orders, "orders"),
            _frame(spark, spark_types, reviews, "reviews"),
            None,
            reference_date,
        )
    finally:
        spark.stop()
    return customer_features, restaurant_features


def run_job(input_dir: Path, output_dir: Path, reference_date: date) -> dict[str, int]:
    """Read prepared Parquet, aggregate in Spark, and write a separate directory."""
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    _reject_overwrite(input_dir, output_dir)
    _validate_inputs(input_dir)
    spark = _session()
    try:
        customers = spark.read.parquet(str(input_dir / "customers.parquet"))
        restaurants = spark.read.parquet(str(input_dir / "restaurants.parquet"))
        orders = spark.read.parquet(str(input_dir / "orders.parquet"))
        reviews = spark.read.parquet(str(input_dir / "reviews.parquet"))
        sentiment = None
        sentiment_path = input_dir / f"{SENTIMENT_FILE}.parquet"
        if sentiment_path.is_file():
            sentiment = spark.read.parquet(str(sentiment_path))
        customer_features, restaurant_features, activity, sentiment_counts = _aggregate(
            spark, customers, restaurants, orders, reviews, sentiment, reference_date
        )
    finally:
        spark.stop()
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_frame(customer_features, output_dir / "customer_features.parquet")
    _write_frame(restaurant_features, output_dir / "restaurant_features.parquet")
    _write_frame(activity, output_dir / "restaurant_activity.parquet")
    written = {
        "customer_features": len(customer_features),
        "restaurant_features": len(restaurant_features),
        "restaurant_activity": len(activity),
    }
    if sentiment_counts is not None:
        _write_frame(sentiment_counts, output_dir / "restaurant_sentiment_counts.parquet")
        written["restaurant_sentiment_counts"] = len(sentiment_counts)
    logger.info("Wrote Spark features to %s", output_dir)
    return written


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success and 1 on input or Spark errors."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Aggregate FoodPulse customer and restaurant features with Spark."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT, help="Directory of prepared Parquet files.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="New directory for Spark feature files. It must not be the input directory.",
    )
    parser.add_argument("--reference-date", default=None, help="UTC calendar date YYYY-MM-DD. Defaults to today.")
    args = parser.parse_args(argv)
    try:
        reference_date = parse_reference_date(args.reference_date)
        run_job(args.input_dir, args.output_dir, reference_date)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _validate_inputs(input_dir: Path) -> None:
    """Check that required files exist and contain the columns the job uses."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory was not found: {input_dir}")
    for name, columns in REQUIRED_FILES.items():
        _require_file(input_dir / f"{name}.parquet", columns)
    sentiment_path = input_dir / f"{SENTIMENT_FILE}.parquet"
    if sentiment_path.is_file():
        _require_file(sentiment_path, SENTIMENT_COLUMNS)
    else:
        logger.info("Optional %s.parquet is absent. Sentiment counts will not be written.", SENTIMENT_FILE)


def _require_file(path: Path, columns: tuple[str, ...]) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required input file was not found: {path}")
    try:
        present = set(pq.read_schema(path).names)
    except Exception as exc:
        raise ValueError(f"{path.name} is not a readable Parquet file") from exc
    missing = [column for column in columns if column not in present]
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")


def _aggregate(spark, customers, restaurants, orders, reviews, sentiment, reference_date: date):
    functions, = (_spark_modules()[1],)
    cutoff = end_of_reference_day(reference_date)
    window_start = cutoff - timedelta(days=ROLLING_RATING_WINDOW_DAYS)
    cutoff_value = functions.lit(cutoff.to_pydatetime())
    window_value = functions.lit(window_start.to_pydatetime())

    completed = orders.filter(
        (functions.lower(functions.col("status")) == COMPLETED_ORDER_STATUS)
        & functions.col("order_date").isNotNull()
        & (functions.col("order_date") <= cutoff_value)
    )
    visible_reviews = reviews.filter(
        functions.col("created_at").isNotNull() & (functions.col("created_at") <= cutoff_value)
    )
    customer_orders = completed.groupBy("customer_id").agg(
        functions.count(functions.lit(1)).alias("order_frequency"),
        functions.sum("total_amount").alias("total_spend"),
        functions.avg("total_amount").alias("avg_order_value"),
        functions.max("order_date").alias("last_order_date"),
        functions.avg(functions.when(functions.col("discount_used") > 0, 1.0).otherwise(0.0)).alias(
            "discount_usage_rate"
        ),
    )
    customer_reviews = visible_reviews.groupBy("customer_id").agg(
        functions.avg("rating").alias("avg_rating"),
        functions.count(functions.lit(1)).alias("review_frequency"),
    )
    customer_base = customers.select(functions.col("id").alias("customer_id")).dropDuplicates(["customer_id"])
    customer_joined = (
        customer_base.join(customer_orders, "customer_id", "left")
        .join(customer_reviews, "customer_id", "left")
        .withColumn("recency_days", functions.datediff(functions.lit(reference_date), functions.to_date("last_order_date")))
        .withColumn("order_frequency", functions.coalesce(functions.col("order_frequency"), functions.lit(0)))
        .withColumn("total_spend", functions.coalesce(functions.col("total_spend"), functions.lit(0.0)))
        .withColumn("review_frequency", functions.coalesce(functions.col("review_frequency"), functions.lit(0)))
        .withColumn("feature_reference_date", functions.lit(reference_date.isoformat()))
    )
    customer_features = _to_pandas(customer_joined.select(*CUSTOMER_FEATURE_COLUMNS), CUSTOMER_FEATURE_COLUMNS)

    restaurant_orders = completed.groupBy("restaurant_id").agg(
        functions.count(functions.lit(1)).alias("order_volume"),
        functions.sum("total_amount").alias("total_spend"),
        functions.avg("total_amount").alias("avg_order_value"),
        functions.countDistinct("customer_id").alias("customer_count"),
    )
    restaurant_reviews = visible_reviews.groupBy("restaurant_id").agg(
        functions.avg("rating").alias("avg_rating"),
        functions.count(functions.lit(1)).alias("review_volume"),
    )
    rolling = (
        visible_reviews.filter(functions.col("created_at") > window_value)
        .groupBy("restaurant_id")
        .agg(functions.avg("rating").alias("rolling_avg_rating"))
    )
    complaints = (
        visible_reviews.filter(functions.col("rating") <= COMPLAINT_RATING_MAX)
        .groupBy("restaurant_id")
        .agg(functions.count(functions.lit(1)).alias("complaint_count"))
    )
    restaurant_base = restaurants.select(functions.col("id").alias("restaurant_id")).dropDuplicates(["restaurant_id"])
    restaurant_joined = (
        restaurant_base.join(restaurant_orders, "restaurant_id", "left")
        .join(restaurant_reviews, "restaurant_id", "left")
        .join(rolling, "restaurant_id", "left")
        .join(complaints, "restaurant_id", "left")
        .withColumn("order_volume", functions.coalesce(functions.col("order_volume"), functions.lit(0)))
        .withColumn("review_volume", functions.coalesce(functions.col("review_volume"), functions.lit(0)))
        .withColumn("complaint_count", functions.coalesce(functions.col("complaint_count"), functions.lit(0)))
        .withColumn("sentiment_label", functions.lit(None).cast("string"))
        .withColumn("sentiment_score", functions.lit(None).cast("double"))
        .withColumn("feature_reference_date", functions.lit(reference_date.isoformat()))
    )
    # Shared columns match the Pandas builder. Spend and customer counts are
    # extra Spark columns and are not part of that contract.
    extra = ("total_spend", "avg_order_value", "customer_count")
    restaurant_pdf = _to_pandas(
        restaurant_joined.select(*RESTAURANT_FEATURE_COLUMNS, *extra),
        RESTAURANT_FEATURE_COLUMNS + extra,
    )
    shared = restaurant_pdf.loc[:, list(RESTAURANT_FEATURE_COLUMNS)].reset_index(drop=True)
    activity = restaurant_pdf.loc[:, ["restaurant_id", "order_volume", "total_spend", "avg_order_value", "customer_count"]].reset_index(drop=True)
    activity["order_volume"] = activity["order_volume"].fillna(0).astype("int64")
    activity["customer_count"] = activity["customer_count"].fillna(0).astype("int64")
    activity["total_spend"] = activity["total_spend"].fillna(0.0)
    sentiment_counts = None
    if sentiment is not None:
        sentiment_counts = _sentiment_counts(functions, visible_reviews, sentiment, restaurant_base)
    logger.info(
        "Spark aggregated %s customers and %s restaurants",
        len(customer_features),
        len(shared),
    )
    return customer_features, shared, activity, sentiment_counts


def _sentiment_counts(functions, reviews, sentiment, restaurant_base):
    labeled = reviews.join(sentiment, reviews["id"] == sentiment["review_id"], "inner")
    counts = labeled.groupBy("restaurant_id").agg(
        functions.count(functions.lit(1)).alias("scored_review_count"),
        *[
            functions.sum(functions.when(functions.col("overall_sentiment") == label, 1).otherwise(0)).alias(
                f"{label}_count"
            )
            for label in SENTIMENT_LABELS
        ],
        functions.avg("overall_score").alias("mean_overall_score"),
    )
    joined = restaurant_base.join(counts, "restaurant_id", "left")
    for label in SENTIMENT_LABELS:
        joined = joined.withColumn(f"{label}_count", functions.coalesce(functions.col(f"{label}_count"), functions.lit(0)))
        joined = joined.withColumn(
            f"{label}_proportion",
            functions.when(
                functions.col("scored_review_count") > 0,
                functions.col(f"{label}_count") / functions.col("scored_review_count"),
            ),
        )
    columns = (
        "restaurant_id",
        "scored_review_count",
        *[f"{label}_count" for label in SENTIMENT_LABELS],
        *[f"{label}_proportion" for label in SENTIMENT_LABELS],
        "mean_overall_score",
    )
    frame = _to_pandas(joined.select(*columns), columns)
    frame["scored_review_count"] = frame["scored_review_count"].fillna(0).astype("int64")
    for label in SENTIMENT_LABELS:
        frame[f"{label}_count"] = frame[f"{label}_count"].fillna(0).astype("int64")
    return frame


def _to_pandas(frame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Collect the aggregated feature rows, not the source orders or reviews."""
    pdf = frame.toPandas()
    if pdf.empty:
        return pd.DataFrame(columns=list(columns))
    return pdf.reset_index(drop=True)


def _frame(spark, spark_types, frame: pd.DataFrame, name: str):
    required = REQUIRED_FILES[name]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")
    slim = frame.loc[:, list(required)].copy()
    for column in ("order_date", "created_at"):
        if column in slim.columns:
            parsed = pd.to_datetime(slim[column], utc=True, errors="coerce", format="mixed")
            slim[column] = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
    if slim.empty:
        fields = []
        for column in required:
            if column in {"total_amount", "discount_used"}:
                fields.append(spark_types.StructField(column, spark_types.DoubleType(), True))
            elif column in {"status",}:
                fields.append(spark_types.StructField(column, spark_types.StringType(), True))
            elif column in {"order_date", "created_at"}:
                fields.append(spark_types.StructField(column, spark_types.TimestampType(), True))
            else:
                fields.append(spark_types.StructField(column, spark_types.LongType(), True))
        return spark.createDataFrame([], spark_types.StructType(fields))
    return spark.createDataFrame(slim)


def _reject_overwrite(input_dir: Path, output_dir: Path) -> None:
    """Allow a new directory, including one nested under the input, but not the ETL files themselves."""
    if output_dir == input_dir:
        raise ValueError(
            f"Refusing to write Spark features into {input_dir}. Choose a different --output-dir."
        )
    protected = (
        "customers.parquet",
        "restaurants.parquet",
        "orders.parquet",
        "reviews.parquet",
        "review_sentiment.parquet",
        "customer_features.parquet",
        "restaurant_features.parquet",
    )
    for name in protected:
        if (output_dir / name).resolve() == (input_dir / name).resolve():
            raise ValueError(f"Refusing to replace the ETL file {input_dir / name}")


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    frame.to_parquet(path, index=False)


def _session():
    spark_session, _functions, _types = _spark_modules()
    return (
        spark_session.builder.master("local[1]")
        .appName("foodpulse-features")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )


def _spark_modules():
    """Import the installed PySpark library, not this repository folder."""
    import importlib
    import site

    removed: list[str] = []
    for key in list(sys.modules):
        if key == "pyspark" or key.startswith("pyspark."):
            module = sys.modules[key]
            location = " ".join(
                [str(getattr(module, "__file__", "") or "")]
                + [str(item) for item in list(getattr(module, "__path__", []) or [])]
            )
            if "site-packages" not in location.replace("\\", "/"):
                del sys.modules[key]
                removed.append(key)
    original_path = sys.path[:]
    sys.path = [entry for entry in original_path if not _shadows_library(entry)]
    for directory in site.getsitepackages():
        if directory not in sys.path:
            sys.path.insert(0, directory)
    try:
        spark_sql = importlib.import_module("pyspark.sql")
        functions = importlib.import_module("pyspark.sql.functions")
        types = importlib.import_module("pyspark.sql.types")
    except ImportError as exc:
        raise RuntimeError(
            "PySpark is not installed in this environment. From the repository root, run "
            '.\\.venv\\Scripts\\python.exe -m pip install "pyspark>=3.5". '
            "Java 17 or 21 is also required. This machine's Java may be newer than PySpark supports."
        ) from exc
    finally:
        sys.path = original_path
    return spark_sql.SparkSession, functions, types


def _shadows_library(entry: str) -> bool:
    candidate = Path(entry).resolve() if entry else Path.cwd().resolve()
    if (candidate / "pyspark" / "jobs" / "feature_aggregations.py").is_file():
        return True
    return candidate.name == "pyspark" and (candidate / "jobs" / "feature_aggregations.py").is_file()


if __name__ == "__main__":
    sys.exit(main())
