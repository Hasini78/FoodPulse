"""Optional Spark aggregations with the same feature definitions.

The default pipeline does not import this module. Set ``USE_SPARK=1`` to use
it. Feature thresholds are imported from
``etl.transform.feature_engineering`` so the complaint rule, completed-order
filter, and 90-day rolling window stay identical to the Pandas path.

This file lives under the repository ``pyspark/jobs`` directory. It is loaded
by file path so the local folder does not have to be an importable package.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from etl.transform.feature_engineering import (
    COMPLAINT_RATING_MAX,
    COMPLETED_ORDER_STATUS,
    ROLLING_RATING_WINDOW_DAYS,
    build_customer_features,
    end_of_reference_day,
)

logger = logging.getLogger(__name__)


def build_features(
    customers: pd.DataFrame,
    restaurants: pd.DataFrame,
    orders: pd.DataFrame,
    reviews: pd.DataFrame,
    *,
    reference_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate features with Spark, then return Pandas frames.

    Spark performs the heavy order and review group-bys. The results are
    joined back to the full customer and restaurant id lists with the same
    null rules as the Pandas implementation.
    """
    try:
        from pyspark.sql import SparkSession
        from pyspark.sql import functions as F
    except ImportError as exc:
        raise RuntimeError(
            "USE_SPARK is set, but PySpark is not installed in this environment. "
            "Unset USE_SPARK to use the Pandas pipeline."
        ) from exc

    spark = (
        SparkSession.builder.master("local[1]")
        .appName("foodpulse-features")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:
        customer_features = _customer_features_spark(
            spark, F, customers, orders, reviews, reference_date
        )
        restaurant_features = _restaurant_features_spark(
            spark, F, restaurants, orders, reviews, reference_date
        )
    finally:
        spark.stop()
    logger.info("Spark feature aggregations finished")
    return customer_features, restaurant_features


def _customer_features_spark(spark, functions, customers, orders, reviews, reference_date: date):
    """Run customer aggregations in Spark and align them to the Pandas schema."""
    # The Pandas builders remain the schema contract. Spark results are checked
    # against that contract by recomputing only through Spark group-bys below,
    # then the shared null-fill rules are applied by merging onto customer ids.
    cutoff = end_of_reference_day(reference_date)
    order_sdf = spark.createDataFrame(_orders_for_spark(orders))
    review_sdf = spark.createDataFrame(_reviews_for_spark(reviews))
    completed = order_sdf.filter(
        (functions.lower(functions.col("status")) == COMPLETED_ORDER_STATUS)
        & (functions.col("order_date") <= functions.lit(cutoff.to_pydatetime()))
    )
    order_agg = completed.groupBy("customer_id").agg(
        functions.count(functions.lit(1)).alias("order_frequency"),
        functions.sum("total_amount").alias("total_spend"),
        functions.avg("total_amount").alias("avg_order_value"),
        functions.max("order_date").alias("last_order_date"),
        functions.avg(functions.when(functions.col("discount_used") > 0, 1.0).otherwise(0.0)).alias(
            "discount_usage_rate"
        ),
    )
    review_agg = review_sdf.filter(
        functions.col("created_at") <= functions.lit(cutoff.to_pydatetime())
    ).groupBy("customer_id").agg(
        functions.avg("rating").alias("avg_rating"),
        functions.count(functions.lit(1)).alias("review_frequency"),
    )
    order_pdf = order_agg.toPandas()
    review_pdf = review_agg.toPandas()
    if not order_pdf.empty:
        last_dates = pd.to_datetime(order_pdf["last_order_date"], utc=True, format="mixed").dt.date
        order_pdf["recency_days"] = last_dates.map(lambda day: (reference_date - day).days)
        order_pdf = order_pdf.drop(columns=["last_order_date"])
    else:
        order_pdf["recency_days"] = pd.Series(dtype="float64")
    base = customers.loc[:, ["id"]].drop_duplicates().rename(columns={"id": "customer_id"})
    features = base.merge(order_pdf, how="left", on="customer_id").merge(
        review_pdf, how="left", on="customer_id"
    )
    # Reuse the Pandas null policy by passing already-filtered frames through
    # the shared builder when Spark returned no rows for an empty input.
    if features.empty:
        return build_customer_features(customers, orders, reviews, reference_date=reference_date)
    features["order_frequency"] = features["order_frequency"].fillna(0).astype("int64")
    features["total_spend"] = features["total_spend"].fillna(0.0)
    features["review_frequency"] = features["review_frequency"].fillna(0).astype("int64")
    features["feature_reference_date"] = reference_date.isoformat()
    from etl.transform.feature_engineering import CUSTOMER_FEATURE_COLUMNS

    return features.loc[:, list(CUSTOMER_FEATURE_COLUMNS)].reset_index(drop=True)


def _restaurant_features_spark(spark, functions, restaurants, orders, reviews, reference_date: date):
    """Run restaurant aggregations in Spark."""
    cutoff = end_of_reference_day(reference_date)
    window_start = cutoff - pd.Timedelta(days=ROLLING_RATING_WINDOW_DAYS)
    order_sdf = spark.createDataFrame(_orders_for_spark(orders))
    review_sdf = spark.createDataFrame(_reviews_for_spark(reviews))
    completed = order_sdf.filter(
        (functions.lower(functions.col("status")) == COMPLETED_ORDER_STATUS)
        & (functions.col("order_date") <= functions.lit(cutoff.to_pydatetime()))
    )
    visible_reviews = review_sdf.filter(
        functions.col("created_at") <= functions.lit(cutoff.to_pydatetime())
    )
    order_agg = completed.groupBy("restaurant_id").agg(
        functions.count(functions.lit(1)).alias("order_volume")
    )
    review_agg = visible_reviews.groupBy("restaurant_id").agg(
        functions.avg("rating").alias("avg_rating"),
        functions.count(functions.lit(1)).alias("review_volume"),
    )
    rolling_agg = visible_reviews.filter(
        functions.col("created_at") > functions.lit(window_start.to_pydatetime())
    ).groupBy("restaurant_id").agg(functions.avg("rating").alias("rolling_avg_rating"))
    complaints = (
        visible_reviews.filter(functions.col("rating") <= COMPLAINT_RATING_MAX)
        .groupBy("restaurant_id")
        .agg(functions.count(functions.lit(1)).alias("complaint_count"))
    )
    base = restaurants.loc[:, ["id"]].drop_duplicates().rename(columns={"id": "restaurant_id"})
    features = (
        base.merge(order_agg.toPandas(), how="left", on="restaurant_id")
        .merge(review_agg.toPandas(), how="left", on="restaurant_id")
        .merge(rolling_agg.toPandas(), how="left", on="restaurant_id")
        .merge(complaints.toPandas(), how="left", on="restaurant_id")
    )
    features["order_volume"] = features["order_volume"].fillna(0).astype("int64")
    features["review_volume"] = features["review_volume"].fillna(0).astype("int64")
    features["complaint_count"] = features["complaint_count"].fillna(0).astype("int64")
    features["sentiment_label"] = pd.Series([pd.NA] * len(features), dtype="string")
    features["sentiment_score"] = pd.Series([pd.NA] * len(features), dtype="Float64")
    features["feature_reference_date"] = reference_date.isoformat()
    from etl.transform.feature_engineering import RESTAURANT_FEATURE_COLUMNS

    return features.loc[:, list(RESTAURANT_FEATURE_COLUMNS)].reset_index(drop=True)


def _orders_for_spark(orders: pd.DataFrame) -> pd.DataFrame:
    frame = orders.copy()
    frame["order_date"] = pd.to_datetime(frame["order_date"], utc=True, format="mixed").dt.tz_localize(None)
    return frame


def _reviews_for_spark(reviews: pd.DataFrame) -> pd.DataFrame:
    frame = reviews.copy()
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True, format="mixed").dt.tz_localize(None)
    return frame
