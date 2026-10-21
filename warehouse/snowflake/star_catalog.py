"""Star-schema tables built from processed Parquet. Separate from snapshot DATASETS.

Snapshot mining tables stay in ``catalog.DATASETS``. These tables are created and
loaded only by ``warehouse.snowflake.run_star``. Identifiers are VARCHAR so they
join the snapshot tables. Surrogate keys are NUMBER values copied from whole
number source ids so a full refresh stays deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from warehouse.snowflake.catalog import Column, Dataset, _float, _identifier, _integer, _text, _timestamp


def _boolean(name: str) -> Column:
    return Column(name, "BOOLEAN", "boolean")


def _date(name: str) -> Column:
    return Column(name, "DATE", "date")


def _surrogate(name: str) -> Column:
    return Column(name, "NUMBER", "integer")


@dataclass(frozen=True)
class StarTable:
    """One star table plus the grain that tests and docs must keep honest."""

    dataset: Dataset
    grain: str
    natural_key: tuple[str, ...]
    source_files: tuple[str, ...]
    skipped_reason: str | None = None

    @property
    def table(self) -> str:
        return self.dataset.table


DIM_DATE = StarTable(
    Dataset(
        "DIM_DATE",
        "orders.parquet",
        (
            _surrogate("date_sk"),
            _date("date_day"),
            _integer("year"),
            _integer("quarter"),
            _integer("month"),
            _text("month_name"),
            _integer("day"),
            _integer("day_of_week"),
            _text("day_name"),
            _boolean("is_weekend"),
        ),
    ),
    grain="One row per UTC calendar date that appears on an order or a review.",
    natural_key=("date_sk",),
    source_files=("orders.parquet", "reviews.parquet"),
)

DIM_CUSTOMER = StarTable(
    Dataset(
        "DIM_CUSTOMER",
        "customers.parquet",
        (
            _surrogate("customer_sk"),
            _identifier("customer_id"),
            _text("city"),
            _text("gender"),
            _timestamp("created_at"),
        ),
    ),
    grain="One row per customer_id from customers.parquet. Given names, contact details, and date of birth are not loaded.",
    natural_key=("customer_id",),
    source_files=("customers.parquet",),
)

DIM_RESTAURANT = StarTable(
    Dataset(
        "DIM_RESTAURANT",
        "restaurants.parquet",
        (
            _surrogate("restaurant_sk"),
            _identifier("restaurant_id"),
            _text("name"),
            _text("cuisine_type"),
            _boolean("is_active"),
            _text("city"),
            _text("state"),
            _text("country"),
            _timestamp("created_at"),
        ),
    ),
    grain="One row per restaurant_id. City, state, and country come from locations.parquet when location_id matches.",
    natural_key=("restaurant_id",),
    source_files=("restaurants.parquet", "locations.parquet"),
)

DIM_FOOD_ITEM = StarTable(
    Dataset(
        "DIM_FOOD_ITEM",
        "food_items.parquet",
        (
            _surrogate("food_item_sk"),
            _identifier("food_item_id"),
            _surrogate("restaurant_sk"),
            _identifier("restaurant_id"),
            _text("name"),
            _text("category"),
            _float("price"),
            _boolean("is_available"),
            _timestamp("created_at"),
        ),
    ),
    grain="One row per food item. restaurant_sk points at DIM_RESTAURANT. There is no fact at this grain.",
    natural_key=("food_item_id",),
    source_files=("food_items.parquet", "restaurants.parquet"),
)

FACT_ORDERS = StarTable(
    Dataset(
        "FACT_ORDERS",
        "orders.parquet",
        (
            _surrogate("order_sk"),
            _identifier("order_id"),
            _surrogate("date_sk"),
            _surrogate("customer_sk"),
            _surrogate("restaurant_sk"),
            _text("status"),
            _float("total_amount"),
            _float("discount_used"),
            _float("total_amount_capped"),
            _boolean("is_total_outlier"),
            _timestamp("order_ts"),
        ),
    ),
    grain="One row per order. Food-item quantity is not at this grain; order_items.parquet is not loaded as a fact.",
    natural_key=("order_id",),
    source_files=("orders.parquet", "customers.parquet", "restaurants.parquet"),
)

FACT_REVIEWS = StarTable(
    Dataset(
        "FACT_REVIEWS",
        "reviews.parquet",
        (
            _surrogate("review_sk"),
            _identifier("review_id"),
            _surrogate("date_sk"),
            _surrogate("customer_sk"),
            _surrogate("restaurant_sk"),
            _surrogate("order_sk"),
            _integer("rating"),
            _timestamp("review_ts"),
        ),
    ),
    grain="One row per review. Review body text is not loaded. order_sk is null when the review has no matching order.",
    natural_key=("review_id",),
    source_files=("reviews.parquet", "customers.parquet", "restaurants.parquet", "orders.parquet"),
)

STAR_TABLES: tuple[StarTable, ...] = (
    DIM_DATE,
    DIM_CUSTOMER,
    DIM_RESTAURANT,
    DIM_FOOD_ITEM,
    FACT_ORDERS,
    FACT_REVIEWS,
)

STAR_DATASETS: tuple[Dataset, ...] = tuple(table.dataset for table in STAR_TABLES)
STAR_BY_TABLE = {table.table: table.dataset for table in STAR_TABLES}
STAR_META = {table.table: table for table in STAR_TABLES}

FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    ("FACT_ORDERS", "date_sk", "DIM_DATE", "date_sk"),
    ("FACT_ORDERS", "customer_sk", "DIM_CUSTOMER", "customer_sk"),
    ("FACT_ORDERS", "restaurant_sk", "DIM_RESTAURANT", "restaurant_sk"),
    ("FACT_REVIEWS", "date_sk", "DIM_DATE", "date_sk"),
    ("FACT_REVIEWS", "customer_sk", "DIM_CUSTOMER", "customer_sk"),
    ("FACT_REVIEWS", "restaurant_sk", "DIM_RESTAURANT", "restaurant_sk"),
    ("DIM_FOOD_ITEM", "restaurant_sk", "DIM_RESTAURANT", "restaurant_sk"),
)

DROPPED_TABLES: tuple[tuple[str, str], ...] = (
    ("DIM_LOCATION", "Not requested. City, state, and country are copied onto DIM_RESTAURANT from locations.parquet."),
    ("DIM_USER", "users.parquet holds hashed passwords and is already excluded from the snapshot loader."),
    ("FACT_ORDER_ITEMS", "Not requested. Attaching food_item_id to FACT_ORDERS would repeat order totals."),
)
