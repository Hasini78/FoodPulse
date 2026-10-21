"""Build and validate the star schema from processed Parquet.

Dry-run never opens Snowflake. Execute reuses the snapshot publisher's staging
and INSERT OVERWRITE path so reruns replace rows instead of appending.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from warehouse.dimensions.customer import EXCLUDED_COLUMNS as CUSTOMER_PII
from warehouse.dimensions.customer import build_customer
from warehouse.dimensions.date import build_date
from warehouse.dimensions.food_item import build_food_item
from warehouse.dimensions.restaurant import EXCLUDED_COLUMNS as RESTAURANT_PII
from warehouse.dimensions.restaurant import build_restaurant
from warehouse.facts.orders import build_orders
from warehouse.facts.reviews import build_reviews
from warehouse.snowflake.catalog import LOADED_AT
from warehouse.snowflake.config import SnowflakeConfig, quote_identifier
from warehouse.snowflake.ddl import session_statements, table_statement
from warehouse.snowflake.load import TablePlan, _digest, _records, publish
from warehouse.snowflake.star_catalog import (
    DROPPED_TABLES,
    FOREIGN_KEYS,
    STAR_META,
    STAR_TABLES,
    StarTable,
)

SQL_DIR = Path(__file__).resolve().parent / "sql"
REVIEWED_SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

REQUIRED_FILES = (
    "customers.parquet",
    "restaurants.parquet",
    "food_items.parquet",
    "orders.parquet",
    "reviews.parquet",
)


@dataclass(frozen=True)
class StarBuild:
    """In-memory star tables plus skip counts from invalid source rows."""

    frames: dict[str, pd.DataFrame]
    skipped: dict[str, int]
    sources: dict[str, Path]
    digests: dict[str, str]


def build_star(processed_dir: Path) -> StarBuild:
    """Read local Parquet and assemble dimensions then facts."""
    sources = {name: processed_dir / name for name in (*REQUIRED_FILES, "locations.parquet")}
    for name in REQUIRED_FILES:
        path = sources[name]
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
    customers = _read(sources["customers.parquet"])
    restaurants = _read(sources["restaurants.parquet"])
    foods = _read(sources["food_items.parquet"])
    orders = _read(sources["orders.parquet"])
    reviews = _read(sources["reviews.parquet"])
    locations = _read(sources["locations.parquet"]) if sources["locations.parquet"].is_file() else pd.DataFrame()
    _require(customers, ("id",), "customers.parquet")
    _require(restaurants, ("id",), "restaurants.parquet")
    _require(foods, ("id", "restaurant_id"), "food_items.parquet")
    _require(orders, ("id", "customer_id", "restaurant_id", "order_date"), "orders.parquet")
    _require(reviews, ("id", "customer_id", "restaurant_id", "created_at"), "reviews.parquet")
    dim_customer = build_customer(customers)
    dim_restaurant = build_restaurant(restaurants, locations)
    dim_food = build_food_item(foods, dim_restaurant)
    fact_orders, skipped_orders = build_orders(orders, dim_customer, dim_restaurant)
    fact_reviews, skipped_reviews = build_reviews(reviews, dim_customer, dim_restaurant, fact_orders)
    dim_date = build_date(
        fact_orders["order_ts"] if not fact_orders.empty else pd.Series(dtype="datetime64[ns, UTC]"),
        fact_reviews["review_ts"] if not fact_reviews.empty else pd.Series(dtype="datetime64[ns, UTC]"),
    )
    frames = {
        "DIM_DATE": dim_date,
        "DIM_CUSTOMER": dim_customer,
        "DIM_RESTAURANT": dim_restaurant,
        "DIM_FOOD_ITEM": dim_food,
        "FACT_ORDERS": fact_orders,
        "FACT_REVIEWS": fact_reviews,
    }
    digests = {str(path): _digest(path) for path in sources.values() if path.is_file()}
    return StarBuild(
        frames,
        {"FACT_ORDERS": skipped_orders, "FACT_REVIEWS": skipped_reviews},
        {name: path for name, path in sources.items() if path.is_file()},
        digests,
    )


def build_star_plan(processed_dir: Path) -> tuple[list[TablePlan], StarBuild]:
    """Validate transformed rows and attach snapshot-style load records."""
    built = build_star(processed_dir)
    loaded_at = datetime.now(timezone.utc)
    plans: list[TablePlan] = []
    for spec in STAR_TABLES:
        frame = built.frames[spec.table]
        missing = [column for column in spec.dataset.required_columns if column not in frame.columns]
        if missing:
            raise ValueError(f"{spec.table} is missing required columns: {', '.join(missing)}")
        path = built.sources[spec.dataset.filename]
        records = tuple(_records(frame.loc[:, list(spec.dataset.required_columns)], spec.dataset, loaded_at))
        plans.append(
            TablePlan(
                spec.table,
                path,
                len(records),
                spec.dataset.required_columns,
                built.digests[str(path)],
                records,
            )
        )
    return plans, built


def validate_star(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Return relationship problems. An empty list means the in-memory model is consistent."""
    problems: list[str] = []
    for spec in STAR_TABLES:
        frame = frames[spec.table]
        for column in spec.natural_key:
            if column not in frame.columns:
                problems.append(f"{spec.table} is missing natural key {column}")
                continue
            duplicated = int(frame[column].duplicated().sum())
            if duplicated:
                problems.append(f"{spec.table} has {duplicated} duplicate {column} values")
            if frame[column].isna().any():
                problems.append(f"{spec.table} has a null {column}")
    for fact, fk, dim, pk in FOREIGN_KEYS:
        fact_frame = frames[fact]
        dim_keys = set(frames[dim][pk].dropna())
        if fact_frame.empty:
            continue
        orphans = fact_frame.loc[~fact_frame[fk].isna() & ~fact_frame[fk].isin(dim_keys)]
        if not orphans.empty:
            problems.append(f"{fact}.{fk} has {len(orphans)} values missing from {dim}.{pk}")
    for column in CUSTOMER_PII + RESTAURANT_PII:
        if column in frames["DIM_CUSTOMER"].columns or column in frames["DIM_RESTAURANT"].columns:
            problems.append(f"PII column {column} must not appear on a dimension")
    if "review_text" in frames["FACT_REVIEWS"].columns:
        problems.append("FACT_REVIEWS must not include review_text")
    if "food_item_id" in frames["FACT_ORDERS"].columns:
        problems.append("FACT_ORDERS must not include food_item_id")
    reviews = frames["FACT_REVIEWS"]
    if not reviews.empty:
        known_orders = set(frames["FACT_ORDERS"]["order_sk"].dropna())
        unknown_orders = reviews.loc[reviews["order_sk"].notna() & ~reviews["order_sk"].isin(known_orders)]
        if not unknown_orders.empty:
            problems.append(f"FACT_REVIEWS.order_sk has {len(unknown_orders)} values missing from FACT_ORDERS")
    return problems


def schema_sql(warehouse: str = "FOODPULSE_WH", database: str = "FOODPULSE", schema: str = "ANALYTICS") -> str:
    """CREATE IF NOT EXISTS for the star tables. Snapshot tables are not listed."""
    lines = [
        "-- Star schema for FOODPULSE.ANALYTICS.",
        "-- Companion to warehouse/snowflake/sql/analytics_tables.sql. Star tables only.",
        "-- CREATE IF NOT EXISTS only. This file does not drop snapshot tables or create a warehouse.",
        "-- DDL commits on its own. A multi-table load is not one atomic snapshot.",
        "-- Grain is documented per table in warehouse/README.md.",
        "-- Live execution uses python -m warehouse.snowflake.run_star --execute, not a local dry-run.",
        "",
    ]
    for statement in session_statements(warehouse, database, schema):
        lines.append(f"{statement};")
        lines.append("")
    for spec in STAR_TABLES:
        lines.append(f"-- {spec.table} grain: {spec.grain}")
        lines.append(f"{table_statement(spec.dataset, database, schema)};")
        lines.append("")
    lines.append("-- Dropped tables")
    for name, reason in DROPPED_TABLES:
        lines.append(f"-- {name}: {reason}")
    return "\n".join(lines).rstrip() + "\n"


def load_sql(database: str = "FOODPULSE", schema: str = "ANALYTICS") -> str:
    """Reviewed repeatable-load statements matching the Python publisher."""
    db = quote_identifier(database)
    sch = quote_identifier(schema)
    lines = [
        "-- Repeatable star-schema load pattern used by python -m warehouse.snowflake.run_star --execute.",
        "-- LIMITATION: this file is not a standalone COPY FROM Parquet script and must not SELECT star",
        "-- rows from snapshot tables. Dimensions and facts are prepared locally (deterministic keys,",
        "-- contact columns omitted, invalid parents skipped). customers.parquet and reviews.parquet are",
        "-- excluded from the snapshot loader, so DIM_CUSTOMER and FACT_REVIEWS cannot be rebuilt from",
        "-- FOODPULSE.ANALYTICS mining snapshots. A stage/COPY process would conflict with the publisher.",
        "-- The Python loader binds prepared rows into a temporary staging table, checks COUNT(*), then",
        "-- INSERT OVERWRITE into the published table. Reruns replace rows; they do not append.",
        "-- Do not run this file against a live account from CI. Do not run it as a local dry-run.",
        "",
    ]
    for spec in STAR_TABLES:
        published = f"{db}.{sch}.{spec.table}"
        staging = f"{db}.{sch}.{spec.table}_LOAD_STAGING"
        columns = ", ".join(column.name.upper() for column in (*spec.dataset.columns, LOADED_AT))
        lines.append(f"CREATE OR REPLACE TEMPORARY TABLE {staging} AS SELECT * FROM {published} WHERE 1 = 0;")
        lines.append(
            f"-- INSERT INTO {staging} ({columns}) VALUES (...) uses bound parameters from the local transform."
        )
        lines.append(f"INSERT OVERWRITE INTO {published} SELECT * FROM {staging};")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def validate_sql(database: str = "FOODPULSE", schema: str = "ANALYTICS") -> str:
    """Row counts, duplicate natural keys, and foreign-key orphans."""
    db = quote_identifier(database)
    sch = quote_identifier(schema)
    catalog = quote_identifier(database)

    def q(table: str) -> str:
        return f"{db}.{sch}.{table}"

    lines = [
        "-- Star-schema validation. Run after a successful --execute load in a Snowflake worksheet.",
        "-- Local dry-run does not execute these statements. Duplicate, null-key, and orphan checks should return 0.",
        "",
    ]
    for spec in STAR_TABLES:
        key = spec.natural_key[0]
        lines.append(f"SELECT '{spec.table}' AS table_name, COUNT(*) AS row_count FROM {q(spec.table)};")
        lines.append(
            f"SELECT '{spec.table}' AS table_name, COUNT(*) - COUNT(DISTINCT {key}) AS duplicate_natural_keys FROM {q(spec.table)};"
        )
        lines.append(
            f"SELECT '{spec.table}' AS table_name, COUNT(*) AS null_natural_keys FROM {q(spec.table)} WHERE {key} IS NULL;"
        )
        lines.append("")
    for fact, fk, dim, pk in FOREIGN_KEYS:
        lines.append(
            "SELECT "
            f"'{fact}.{fk}' AS relationship, COUNT(*) AS orphan_rows "
            f"FROM {q(fact)} fact LEFT JOIN {q(dim)} dim ON fact.{fk} = dim.{pk} "
            f"WHERE fact.{fk} IS NOT NULL AND dim.{pk} IS NULL;"
        )
        lines.append("")
    lines.append(
        f"SELECT COUNT(*) AS reviews_with_unknown_order FROM {q('FACT_REVIEWS')} "
        f"WHERE order_sk IS NOT NULL AND order_sk NOT IN (SELECT order_sk FROM {q('FACT_ORDERS')});"
    )
    lines.append(
        f"SELECT COUNT(*) AS orders_missing_required_keys FROM {q('FACT_ORDERS')} "
        "WHERE date_sk IS NULL OR customer_sk IS NULL OR restaurant_sk IS NULL;"
    )
    lines.append(
        f"SELECT COUNT(*) AS reviews_missing_required_keys FROM {q('FACT_REVIEWS')} "
        "WHERE date_sk IS NULL OR customer_sk IS NULL OR restaurant_sk IS NULL;"
    )
    lines.append(
        f"SELECT COUNT(*) AS food_items_missing_restaurant FROM {q('DIM_FOOD_ITEM')} WHERE restaurant_sk IS NULL;"
    )
    lines.append("")
    lines.append(
        f"SELECT COUNT(*) AS unexpected_customer_contact_columns FROM {catalog}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE table_schema = '{sch}' AND table_name = 'DIM_CUSTOMER' "
        "AND column_name IN ('EMAIL', 'PHONE', 'FIRST_NAME', 'LAST_NAME', 'DATE_OF_BIRTH');"
    )
    lines.append(
        f"SELECT COUNT(*) AS unexpected_restaurant_contact_columns FROM {catalog}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE table_schema = '{sch}' AND table_name = 'DIM_RESTAURANT' "
        "AND column_name IN ('EMAIL', 'PHONE');"
    )
    lines.append(
        f"SELECT COUNT(*) AS unexpected_review_body_columns FROM {catalog}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE table_schema = '{sch}' AND table_name = 'FACT_REVIEWS' "
        "AND column_name IN ('REVIEW_TEXT');"
    )
    lines.append(
        f"SELECT COUNT(*) AS unexpected_order_line_columns FROM {catalog}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE table_schema = '{sch}' AND table_name = 'FACT_ORDERS' "
        "AND column_name IN ('FOOD_ITEM_ID');"
    )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def publish_star(config: SnowflakeConfig, processed_dir: Path, connector=None) -> list[TablePlan]:
    """Connect and replace each star table. Dry-run callers must not use this."""
    plans, built = build_star_plan(processed_dir)
    problems = validate_star(built.frames)
    if problems:
        raise ValueError("; ".join(problems))
    _ensure_sources(built)
    kwargs = {"plans": plans}
    if connector is not None:
        kwargs["connector"] = connector
    published = publish(config, **kwargs)
    _ensure_sources(built)
    return published


def report(built: StarBuild, plans: list[TablePlan]) -> list[dict[str, object]]:
    """Compact dry-run payload."""
    items = []
    for plan in plans:
        spec: StarTable = STAR_META[plan.table]
        items.append(
            {
                "table": plan.table,
                "rows": plan.rows,
                "grain": spec.grain,
                "natural_key": spec.natural_key,
                "skipped": built.skipped.get(plan.table, 0),
                "columns": plan.columns,
            }
        )
    return items


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _require(frame: pd.DataFrame, columns: tuple[str, ...], filename: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{filename} is missing required columns: {', '.join(missing)}")


def _ensure_sources(built: StarBuild) -> None:
    for path_text, digest in built.digests.items():
        if _digest(Path(path_text)) != digest:
            raise RuntimeError("A star-schema source file changed after validation. No further table was published.")
