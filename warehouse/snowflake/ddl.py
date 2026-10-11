"""CREATE IF NOT EXISTS statements for the analytical schema.

The virtual warehouse is not created here. Creating a warehouse can consume
credits and is an account-level step documented in the README.

Snowflake commits DDL on its own. Creating the database, schema, or an empty
table is therefore not part of the later data transaction. A load of several
tables commits one snapshot at a time and is not atomic across tables.
"""

from __future__ import annotations

from warehouse.snowflake.catalog import DATASETS, LOADED_AT, Dataset
from warehouse.snowflake.config import quote_identifier


def session_statements(warehouse: str, database: str, schema: str) -> list[str]:
    """Return warehouse, database, and schema statements. No warehouse is created."""
    warehouse_name = quote_identifier(warehouse)
    database_name = quote_identifier(database)
    schema_name = quote_identifier(schema)
    return [
        f"USE WAREHOUSE {warehouse_name}",
        f"CREATE DATABASE IF NOT EXISTS {database_name}",
        f"CREATE SCHEMA IF NOT EXISTS {database_name}.{schema_name}",
        f"USE DATABASE {database_name}",
        f"USE SCHEMA {schema_name}",
    ]


def setup_statements(database: str, schema: str, datasets: tuple[Dataset, ...] | None = None) -> list[str]:
    """Return non-destructive setup SQL for the selected datasets."""
    chosen = DATASETS if datasets is None else datasets
    statements = [
        f"CREATE DATABASE IF NOT EXISTS {quote_identifier(database)}",
        f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(database)}.{quote_identifier(schema)}",
    ]
    statements.extend(table_statement(dataset, database, schema) for dataset in chosen)
    return statements


def table_statement(dataset: Dataset, database: str, schema: str) -> str:
    """Return CREATE TABLE IF NOT EXISTS for one approved dataset."""
    database_name = quote_identifier(database)
    schema_name = quote_identifier(schema)
    columns = [_column_sql(column.name, column.snowflake_type) for column in dataset.columns]
    columns.append(_column_sql(LOADED_AT.name, LOADED_AT.snowflake_type))
    body = ", ".join(columns)
    return f"CREATE TABLE IF NOT EXISTS {database_name}.{schema_name}.{dataset.table} ({body})"


def staging_name(table: str) -> str:
    """Temporary staging table name for one published table."""
    return quote_identifier(f"{table}_LOAD_STAGING")


def _column_sql(name: str, snowflake_type: str) -> str:
    return f"{quote_identifier(name)} {snowflake_type}"
