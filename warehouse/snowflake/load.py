"""Validate local Parquet files and publish complete Snowflake snapshots.

Dry-run never opens a connection. Execute validates every selected file before
connecting and loads those validated rows. A changed file aborts before the
next write. Rows are inserted into a temporary staging table with bound
parameters. ``INSERT OVERWRITE`` runs in the same transaction and is committed
only after the published count matches.

Snowflake commits DDL on its own, so ``CREATE TABLE IF NOT EXISTS`` can leave
an empty table if the first load fails before a successful overwrite. Each
table is committed separately. A multi-table load is not one atomic snapshot.
The warehouse is never created here.
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd

from warehouse.snowflake.catalog import EXCLUDED_FILES, LOADED_AT, Dataset, select_datasets
from warehouse.snowflake.config import SnowflakeConfig, redact
from warehouse.snowflake.connection import connect
from warehouse.snowflake.ddl import session_statements, staging_name, table_statement

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000
_AUTOCOMMIT_OFF = (
    "Snowflake autocommit could not be disabled. No database objects were created and no data was written."
)


@dataclass(frozen=True)
class TablePlan:
    """One validated local file and the rows that will be loaded from it."""

    table: str
    path: Path
    rows: int
    columns: tuple[str, ...]
    digest: str
    records: tuple[tuple, ...]

    def __repr__(self) -> str:
        return f"TablePlan(table={self.table!r}, rows={self.rows})"


def build_plan(processed_dir: Path, tables: list[str] | None = None) -> list[TablePlan]:
    """Read and validate the approved files. Missing files or columns raise immediately."""
    loaded_at = datetime.now(timezone.utc)
    plans: list[TablePlan] = []
    for dataset in select_datasets(tables):
        if dataset.filename in EXCLUDED_FILES:
            raise ValueError(f"{dataset.filename} is excluded from the Snowflake load")
        path = processed_dir / dataset.filename
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        frame = pd.read_parquet(BytesIO(payload))
        missing = [column for column in dataset.required_columns if column not in frame.columns]
        if missing:
            raise ValueError(f"{dataset.filename} is missing required columns: {', '.join(missing)}")
        if _digest(path) != digest:
            raise RuntimeError(f"{dataset.table} input changed during validation")
        frame = frame.loc[:, list(dataset.required_columns)]
        records = tuple(_records(frame, dataset, loaded_at))
        plans.append(TablePlan(dataset.table, path, len(records), dataset.required_columns, digest, records))
    return plans


def publish(
    config: SnowflakeConfig,
    processed_dir: Path | None = None,
    tables: list[str] | None = None,
    connector=connect,
    plans: list[TablePlan] | None = None,
) -> list[TablePlan]:
    """Validate every selected file, then connect and replace each snapshot."""
    if plans is None:
        if processed_dir is None:
            raise ValueError("A processed directory or a validated plan is required")
        plans = build_plan(processed_dir, tables)
    _ensure_stable(plans)
    try:
        connection = connector(config)
    except Exception as exc:
        raise RuntimeError(_sanitize(config, exc)) from None
    try:
        cursor = connection.cursor()
        try:
            _disable_autocommit(connection, cursor, config)
            _ensure_stable(plans)
            _prepare_session(cursor, config, plans)
            for plan in plans:
                try:
                    _ensure_stable([plan])
                    _publish_one(cursor, config, plan)
                    connection.commit()
                except Exception as exc:
                    _rollback(connection, config)
                    raise RuntimeError(_sanitize(config, RuntimeError(f"{plan.table} was not published. {exc}"))) from None
        finally:
            cursor.close()
    finally:
        connection.close()
    logger.info("Published %s Snowflake snapshots", len(plans))
    return plans


def _disable_autocommit(connection, cursor, config: SnowflakeConfig) -> None:
    """Abort before setup DDL when autocommit cannot be turned off and verified."""
    try:
        if not hasattr(connection, "autocommit"):
            raise RuntimeError("the connection does not expose autocommit control")
        connection.autocommit(False)
        cursor.execute("SHOW PARAMETERS LIKE 'AUTOCOMMIT'")
        row = cursor.fetchone()
    except Exception as exc:
        raise RuntimeError(_sanitize(config, RuntimeError(f"{_AUTOCOMMIT_OFF} {exc}"))) from None
    value = "" if row is None or len(row) < 2 or row[1] is None else str(row[1])
    if value.lower() != "false":
        raise RuntimeError(_AUTOCOMMIT_OFF)


def _prepare_session(cursor, config: SnowflakeConfig, plans: list[TablePlan]) -> None:
    """Check the warehouse, then create only the database, schema, and selected tables."""
    for statement in session_statements(config.warehouse, config.database, config.schema):
        _execute(cursor, statement, config, "use the warehouse or create the database and schema")
    _execute(cursor, "SELECT CURRENT_WAREHOUSE()", config, "use the warehouse")
    current = cursor.fetchone()
    active = "" if current is None or current[0] is None else str(current[0])
    if active.upper() != config.warehouse:
        raise RuntimeError(
            f"Warehouse {config.warehouse} is not active. Create it in the Snowflake UI and grant USAGE. "
            "The loader does not create a warehouse."
        )
    for plan in plans:
        dataset = _dataset(plan.table)
        _execute(
            cursor,
            table_statement(dataset, config.database, config.schema),
            config,
            f"create {dataset.table}",
        )


def _publish_one(cursor, config: SnowflakeConfig, plan: TablePlan) -> None:
    dataset = _dataset(plan.table)
    database = config.database
    schema = config.schema
    published = f"{database}.{schema}.{dataset.table}"
    staging = f"{database}.{schema}.{staging_name(dataset.table)}"
    column_sql = ", ".join(column.name.upper() for column in (*dataset.columns, LOADED_AT))
    _execute(
        cursor,
        f"CREATE OR REPLACE TEMPORARY TABLE {staging} AS SELECT * FROM {published} WHERE 1 = 0",
        config,
        f"create staging for {dataset.table}",
    )
    if len(plan.records) != plan.rows:
        raise RuntimeError(f"{dataset.table} staging row count did not match the validated file")
    placeholders = ", ".join(["?"] * (len(dataset.columns) + 1))
    insert_sql = f"INSERT INTO {staging} ({column_sql}) VALUES ({placeholders})"
    records = list(plan.records)
    for start in range(0, len(records), BATCH_SIZE):
        cursor.executemany(insert_sql, records[start : start + BATCH_SIZE])
    _execute(cursor, f"SELECT COUNT(*) FROM {staging}", config, f"count {dataset.table}")
    staged = int(cursor.fetchone()[0])
    if staged != plan.rows:
        raise RuntimeError(f"{dataset.table} staging validation failed: expected {plan.rows} rows, found {staged}")
    _execute(cursor, f"INSERT OVERWRITE INTO {published} SELECT * FROM {staging}", config, f"publish {dataset.table}")
    _execute(cursor, f"SELECT COUNT(*) FROM {published}", config, f"count {dataset.table}")
    published_count = int(cursor.fetchone()[0])
    if published_count != plan.rows:
        raise RuntimeError(f"{dataset.table} was not published because the snapshot count was {published_count}")


def _execute(cursor, statement: str, config: SnowflakeConfig, context: str) -> None:
    try:
        cursor.execute(statement)
    except Exception as exc:
        raise RuntimeError(_failure_message(config, exc, context)) from None


def _rollback(connection, config: SnowflakeConfig) -> None:
    try:
        connection.rollback()
    except Exception as exc:
        logger.error("Rollback failed. %s", _sanitize(config, exc))


def _ensure_stable(plans: list[TablePlan]) -> None:
    for plan in plans:
        if _digest(plan.path) != plan.digest:
            raise RuntimeError(f"{plan.table} input changed after validation. No further snapshot was published.")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset(table: str) -> Dataset:
    from warehouse.snowflake.catalog import DATASETS_BY_TABLE

    return DATASETS_BY_TABLE[table]


def _failure_message(config: SnowflakeConfig, exc: Exception, context: str) -> str:
    detail = _sanitize(config, exc)
    lowered = detail.lower()
    if "does not exist" in lowered or "not authorized" in lowered:
        return (
            f"The configured role cannot {context}. Create the warehouse in the Snowflake UI if it is missing. "
            "The loader does not create a warehouse. "
            f"Snowflake reported: {detail}"
        )
    if "privilege" in lowered or "access control" in lowered:
        return (
            f"The configured role cannot {context}. Grant USAGE on the warehouse, CREATE DATABASE, "
            "USAGE and CREATE SCHEMA on the database, USAGE and CREATE TABLE on the schema, "
            "and SELECT, INSERT, and DELETE on each published table. "
            f"Snowflake reported: {detail}"
        )
    return detail


def _sanitize(config: SnowflakeConfig, exc: Exception) -> str:
    return redact(str(exc), config.secrets())


def _records(frame: pd.DataFrame, dataset: Dataset, loaded_at: datetime) -> list[tuple]:
    records: list[tuple] = []
    kinds = [column.kind for column in dataset.columns]
    for row in frame.itertuples(index=False, name=None):
        values = [_value(value, kind) for value, kind in zip(row, kinds)]
        values.append(loaded_at)
        records.append(tuple(values))
    return records


def _value(value: object, kind: str):
    if _is_missing(value):
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes, datetime)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if kind == "id":
        return _identifier_text(value)
    if kind == "integer":
        return int(value)
    if kind == "float":
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    if kind == "timestamp":
        if isinstance(value, datetime):
            return value
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    return str(value)


def _identifier_text(value: object) -> str:
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return False
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if isinstance(missing, bool):
        return missing
    return False
