"""Approved Snowflake tables and the Parquet files that feed them.

Identifiers are VARCHAR so integer keys and the string keys used by
recommendations and forecasts join as the same type. ``loaded_at`` is added
by the loader and is not read from Parquet.
"""

from __future__ import annotations

from dataclasses import dataclass

EXCLUDED_FILES = (
    "users.parquet",
    "customers.parquet",
    "reviews.parquet",
    "demand_forecast_history.parquet",
)


@dataclass(frozen=True)
class Column:
    """One Snowflake column loaded from Parquet."""

    name: str
    snowflake_type: str
    kind: str


@dataclass(frozen=True)
class Dataset:
    """One analytical snapshot table."""

    table: str
    filename: str
    columns: tuple[Column, ...]

    @property
    def required_columns(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


def _text(name: str) -> Column:
    return Column(name, "VARCHAR", "text")


def _identifier(name: str) -> Column:
    return Column(name, "VARCHAR", "id")


def _integer(name: str) -> Column:
    return Column(name, "NUMBER", "integer")


def _float(name: str) -> Column:
    return Column(name, "FLOAT", "float")


def _timestamp(name: str) -> Column:
    return Column(name, "TIMESTAMP_TZ", "timestamp")


def _counts(*names: str) -> tuple[Column, ...]:
    return tuple(_integer(name) for name in names)


def _measures(*names: str) -> tuple[Column, ...]:
    return tuple(_float(name) for name in names)


_SENTIMENT_COUNTS = (
    _integer("review_count"),
    *_counts("positive_count", "negative_count", "neutral_count", "invalid_count"),
    _float("mean_score"),
)

DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "REVIEW_SENTIMENT",
        "review_sentiment.parquet",
        (
            _identifier("review_id"),
            _text("overall_sentiment"),
            _float("overall_score"),
            _text("food_sent"),
            _text("service_sent"),
            _text("ambience_sent"),
            _text("price_sent"),
            _timestamp("analyzed_at"),
        ),
    ),
    Dataset("SENTIMENT_BY_RESTAURANT", "sentiment_by_restaurant.parquet", (_identifier("restaurant_id"), *_SENTIMENT_COUNTS)),
    Dataset("SENTIMENT_BY_CITY", "sentiment_by_city.parquet", (_text("city"), *_SENTIMENT_COUNTS)),
    Dataset("SENTIMENT_BY_CUISINE", "sentiment_by_cuisine.parquet", (_text("cuisine_type"), *_SENTIMENT_COUNTS)),
    Dataset("SENTIMENT_BY_MONTH", "sentiment_by_month.parquet", (_text("month"), *_SENTIMENT_COUNTS)),
    Dataset(
        "CUSTOMER_SEGMENTS",
        "customer_segments.parquet",
        (_identifier("customer_id"), _integer("cluster_id"), _text("segment_label")),
    ),
    Dataset(
        "CUSTOMER_SEGMENT_SUMMARY",
        "customer_segment_summary.parquet",
        (
            _integer("cluster_id"),
            _text("segment_label"),
            _integer("count"),
            _float("percent"),
            *_measures(
                "mean_recency_days",
                "median_recency_days",
                "mean_order_frequency",
                "median_order_frequency",
                "mean_total_spend",
                "median_total_spend",
                "mean_avg_order_value",
                "median_avg_order_value",
                "mean_avg_discount",
                "median_avg_discount",
                "mean_avg_rating",
                "median_avg_rating",
                "mean_avg_sentiment_score",
                "median_avg_sentiment_score",
            ),
        ),
    ),
    Dataset(
        "ASSOCIATION_FREQUENT_ITEMSETS",
        "association_frequent_itemsets.parquet",
        (
            _text("item_ids"),
            _text("item_names"),
            _integer("itemset_size"),
            _integer("support_count"),
            _float("support"),
            _text("restaurant_scope"),
        ),
    ),
    Dataset(
        "ASSOCIATION_RULES",
        "association_rules.parquet",
        (
            _text("antecedent_ids"),
            _text("antecedent_names"),
            _text("consequent_ids"),
            _text("consequent_names"),
            _integer("support_count"),
            _float("support"),
            _float("confidence"),
            _float("lift"),
            _float("leverage"),
            _float("conviction"),
            _text("restaurant_scope"),
        ),
    ),
    Dataset(
        "CUSTOMER_CHURN_RISK",
        "customer_churn_risk.parquet",
        (
            _identifier("customer_id"),
            _integer("inactivity_days"),
            _integer("observation_days"),
            _integer("order_frequency"),
            _float("total_spend"),
            _float("avg_order_value"),
            _float("avg_discount"),
            _float("discount_usage_rate"),
            _float("avg_rating"),
            _integer("review_frequency"),
            _float("avg_sentiment_score"),
            _float("mean_purchase_gap_days"),
            _float("purchase_gap_std_days"),
            _integer("recent_order_count"),
            _integer("prior_order_count"),
            _float("risk_score"),
            _text("risk_category"),
            _text("reason_codes"),
        ),
    ),
    Dataset(
        "CUSTOMER_CHURN_SUMMARY",
        "customer_churn_summary.parquet",
        (
            _text("risk_category"),
            _integer("customer_count"),
            _float("share"),
            *_measures(
                "median_inactivity_days",
                "median_order_frequency",
                "median_total_spend",
                "median_avg_order_value",
                "median_avg_rating",
                "median_avg_sentiment_score",
            ),
        ),
    ),
    Dataset(
        "FOOD_RECOMMENDATIONS",
        "food_recommendations.parquet",
        (
            _identifier("customer_id"),
            _identifier("food_item_id"),
            _identifier("restaurant_id"),
            _float("recommendation_score"),
            _integer("rank"),
            _text("reason"),
        ),
    ),
    Dataset(
        "RESTAURANT_RECOMMENDATIONS",
        "restaurant_recommendations.parquet",
        (
            _identifier("customer_id"),
            _identifier("restaurant_id"),
            _float("recommendation_score"),
            _integer("rank"),
            _text("reason"),
        ),
    ),
    Dataset(
        "DEMAND_FORECASTS",
        "demand_forecasts.parquet",
        (
            _text("level"),
            _identifier("restaurant_id"),
            _identifier("food_item_id"),
            _timestamp("forecast_date"),
            _integer("horizon_step"),
            _integer("horizon"),
            _text("aggregation"),
            _text("model_name"),
            _float("predicted_demand"),
            _text("forecast_role"),
            _float("evaluation_mae"),
            _float("evaluation_rmse"),
            _float("evaluation_wape"),
        ),
    ),
    Dataset(
        "CUSTOMER_FEATURES",
        "customer_features.parquet",
        (
            _identifier("customer_id"),
            _integer("recency_days"),
            _integer("order_frequency"),
            _float("total_spend"),
            _float("avg_order_value"),
            _float("avg_rating"),
            _integer("review_frequency"),
            _float("discount_usage_rate"),
            _text("feature_reference_date"),
        ),
    ),
    Dataset(
        "RESTAURANT_FEATURES",
        "restaurant_features.parquet",
        (
            _identifier("restaurant_id"),
            _float("avg_rating"),
            _float("rolling_avg_rating"),
            _integer("review_volume"),
            _integer("order_volume"),
            _integer("complaint_count"),
            _text("sentiment_label"),
            _float("sentiment_score"),
            _text("feature_reference_date"),
        ),
    ),
)

DATASETS_BY_TABLE = {dataset.table: dataset for dataset in DATASETS}
LOADED_AT = Column("loaded_at", "TIMESTAMP_TZ", "timestamp")


def select_datasets(names: list[str] | None) -> tuple[Dataset, ...]:
    """Return the default plan, or the requested approved tables."""
    if not names:
        return DATASETS
    chosen: list[Dataset] = []
    unknown: list[str] = []
    for name in names:
        dataset = DATASETS_BY_TABLE.get(name.strip().upper())
        if dataset is None:
            unknown.append(name)
        else:
            chosen.append(dataset)
    if unknown:
        approved = ", ".join(dataset.table for dataset in DATASETS)
        raise ValueError(f"Unknown table selection: {', '.join(unknown)}. Approved tables: {approved}")
    return tuple(chosen)
