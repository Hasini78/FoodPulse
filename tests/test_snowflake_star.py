"""Star-schema tests. No credentials and no Snowflake network."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from warehouse.dimensions.customer import EXCLUDED_COLUMNS as CUSTOMER_PII
from warehouse.snowflake.catalog import DATASETS_BY_TABLE, EXCLUDED_FILES
from warehouse.snowflake.config import SnowflakeConfig
from warehouse.snowflake.ddl import session_statements, setup_statements, table_statement
from warehouse.snowflake.run_star import main
from warehouse.snowflake.star import (
    REVIEWED_SQL_DIR,
    SQL_DIR,
    build_star,
    build_star_plan,
    load_sql,
    publish_star,
    schema_sql,
    validate_sql,
    validate_star,
)
from warehouse.snowflake.star_catalog import FOREIGN_KEYS, STAR_BY_TABLE, STAR_TABLES


SECRET_PASSWORD = "snowflake-password-should-not-leak"


def _config() -> SnowflakeConfig:
    return SnowflakeConfig(
        account="account-locator.should-not-leak.snowflakecomputing.com",
        user="loader",
        password=SECRET_PASSWORD,
        warehouse="FOODPULSE_WH",
        database="FOODPULSE",
        schema="ANALYTICS",
        role=None,
    )


def _write(directory: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(directory / name, index=False)


def _world(directory: Path) -> None:
    _write(
        directory,
        "customers.parquet",
        pd.DataFrame(
            {
                "id": [1, 1, 2],
                "first_name": ["Ada", "Ada", "Bob"],
                "last_name": ["Lee", "Lee", "Ray"],
                "email": ["ada@example.com", "ada@example.com", "bob@example.com"],
                "phone": ["111", "111", "222"],
                "city": ["Pune", "Pune", "Mumbai"],
                "date_of_birth": [pd.Timestamp("1990-01-01"), pd.Timestamp("1990-01-01"), pd.Timestamp("1991-02-02")],
                "gender": ["F", "F", "M"],
                "created_at": [pd.Timestamp("2026-01-01T00:00:00Z")] * 3,
            }
        ),
    )
    _write(
        directory,
        "restaurants.parquet",
        pd.DataFrame(
            {
                "id": [10, 11],
                "name": ["Thai House", "Spice Room"],
                "cuisine_type": ["Thai", "Indian"],
                "description": ["A", "B"],
                "phone": ["555", "556"],
                "email": ["thai@example.com", "spice@example.com"],
                "location_id": [5, 6],
                "is_active": [True, True],
                "created_at": [pd.Timestamp("2026-01-01T00:00:00Z")] * 2,
            }
        ),
    )
    _write(directory, "locations.parquet", pd.DataFrame({"id": [5, 6], "city": ["Pune", "Mumbai"], "state": ["MH", "MH"], "country": ["IN", "IN"]}))
    _write(
        directory,
        "food_items.parquet",
        pd.DataFrame(
            {
                "id": [100, 101, 199],
                "restaurant_id": [10, 10, 99],
                "name": ["Pad Thai", "Spring Roll", "Orphan"],
                "category": ["Main", "Starter", "Main"],
                "description": ["x", "y", "z"],
                "price": [12.0, 6.0, 1.0],
                "is_available": [True, True, True],
                "created_at": [pd.Timestamp("2026-01-01T00:00:00Z")] * 3,
            }
        ),
    )
    _write(
        directory,
        "orders.parquet",
        pd.DataFrame(
            {
                "id": [1000, 1001, 1002],
                "customer_id": [1, 2, 9],
                "restaurant_id": [10, 11, 10],
                "total_amount": [20.0, 15.0, 9.0],
                "discount_used": [1.0, 0.0, 0.0],
                "status": ["completed", "cancelled", "completed"],
                "order_date": [
                    pd.Timestamp("2026-10-01T10:00:00Z"),
                    pd.Timestamp("2026-10-02T11:00:00Z"),
                    pd.Timestamp("2026-10-03T12:00:00Z"),
                ],
                "created_at": [pd.Timestamp("2026-10-01T10:00:00Z")] * 3,
                "is_total_outlier": [False, False, False],
                "total_amount_capped": [20.0, 15.0, 9.0],
            }
        ),
    )
    _write(
        directory,
        "reviews.parquet",
        pd.DataFrame(
            {
                "id": [7, 8],
                "customer_id": [1, 2],
                "restaurant_id": [10, 11],
                "order_id": [1000, 9999],
                "rating": [5, 3],
                "review_text": ["great", "ok"],
                "created_at": [pd.Timestamp("2026-10-01T18:00:00Z"), pd.Timestamp("2026-10-04T18:00:00Z")],
            }
        ),
    )


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.batches: list[list[tuple]] = []
        self.staged = 0
        self._row = None

    def execute(self, statement: str, _params=None) -> None:
        self.statements.append(statement)
        if "CREATE OR REPLACE TEMPORARY" in statement:
            self.staged = 0
        if statement == "SHOW PARAMETERS LIKE 'AUTOCOMMIT'":
            self._row = ("AUTOCOMMIT", "false")
        elif statement == "SELECT CURRENT_WAREHOUSE()":
            self._row = ("FOODPULSE_WH",)
        elif statement.startswith("SELECT COUNT(*)"):
            self._row = (self.staged,)

    def executemany(self, statement: str, rows) -> None:
        self.statements.append(statement)
        batch = list(rows)
        self.batches.append(batch)
        self.staged += len(batch)

    def fetchone(self):
        return self._row

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_obj = cursor
        self.commits = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_obj

    def autocommit(self, _mode: bool) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_dimensions_drop_pii_and_duplicate_customers(tmp_path: Path) -> None:
    _world(tmp_path)
    built = build_star(tmp_path)
    customers = built.frames["DIM_CUSTOMER"]
    assert list(customers["customer_id"]) == ["1", "2"]
    for column in CUSTOMER_PII:
        assert column not in customers.columns
    restaurants = built.frames["DIM_RESTAURANT"]
    assert "phone" not in restaurants.columns
    assert "email" not in restaurants.columns
    assert restaurants.loc[restaurants["restaurant_id"] == "10", "city"].iloc[0] == "Pune"
    foods = built.frames["DIM_FOOD_ITEM"]
    assert list(foods["food_item_id"]) == ["100", "101"]
    assert "199" not in set(foods["food_item_id"])


def test_fact_grains_skip_invalid_rows_and_keep_status(tmp_path: Path) -> None:
    _world(tmp_path)
    built = build_star(tmp_path)
    orders = built.frames["FACT_ORDERS"]
    assert list(orders["order_id"]) == ["1000", "1001"]
    assert "cancelled" in set(orders["status"])
    assert "food_item_id" not in orders.columns
    assert built.skipped["FACT_ORDERS"] == 1
    reviews = built.frames["FACT_REVIEWS"]
    assert list(reviews["review_id"]) == ["7", "8"]
    assert "review_text" not in reviews.columns
    assert reviews.loc[reviews["review_id"] == "7", "order_sk"].iloc[0] == 1000
    assert pd.isna(reviews.loc[reviews["review_id"] == "8", "order_sk"].iloc[0])
    dates = set(built.frames["DIM_DATE"]["date_sk"])
    assert dates == {20261001, 20261002, 20261004}


def test_keys_are_deterministic_and_relationships_hold(tmp_path: Path) -> None:
    _world(tmp_path)
    first = build_star(tmp_path)
    second = build_star(tmp_path)
    for table in first.frames:
        pd.testing.assert_frame_equal(first.frames[table], second.frames[table])
    assert validate_star(first.frames) == []
    orders = first.frames["FACT_ORDERS"]
    assert set(orders["customer_sk"]).issubset(set(first.frames["DIM_CUSTOMER"]["customer_sk"]))
    assert set(orders["restaurant_sk"]).issubset(set(first.frames["DIM_RESTAURANT"]["restaurant_sk"]))
    assert set(orders["date_sk"]).issubset(set(first.frames["DIM_DATE"]["date_sk"]))


def test_missing_file_and_column_fail_before_connection(tmp_path: Path) -> None:
    calls = {"count": 0}

    def _connect(_config):
        calls["count"] += 1
        raise AssertionError("connect")

    with pytest.raises(FileNotFoundError):
        build_star(tmp_path)
    _world(tmp_path)
    frame = pd.read_parquet(tmp_path / "orders.parquet")
    frame.drop(columns=["customer_id"]).to_parquet(tmp_path / "orders.parquet", index=False)
    with pytest.raises(ValueError, match="customer_id"):
        build_star(tmp_path)
    assert calls["count"] == 0


def test_sql_generation_matches_reviewed_files() -> None:
    schema = schema_sql()
    load = load_sql()
    checks = validate_sql()
    for directory in (SQL_DIR, REVIEWED_SQL_DIR):
        assert (directory / "star_schema.sql").is_file()
        assert (directory / "star_load.sql").is_file()
        assert (directory / "star_validate.sql").is_file()
        assert schema == (directory / "star_schema.sql").read_text(encoding="utf-8")
        assert load == (directory / "star_load.sql").read_text(encoding="utf-8")
        assert checks == (directory / "star_validate.sql").read_text(encoding="utf-8")
    for spec in STAR_TABLES:
        assert spec.table in schema
        assert spec.table in load
        assert spec.table in checks
        assert table_statement(spec.dataset, "FOODPULSE", "ANALYTICS") in schema
        assert spec.grain in schema
        assert spec.natural_key[0] in checks
        for column in spec.dataset.columns:
            assert column.name.upper() in schema
            assert column.name.upper() in load
    for statement in session_statements("FOODPULSE_WH", "FOODPULSE", "ANALYTICS"):
        assert statement in schema
    for fact, fk, dim, pk in FOREIGN_KEYS:
        assert fact in checks
        assert fk in checks
        assert dim in checks
        assert pk in checks
    upper = schema.upper()
    assert "DROP TABLE" not in upper
    assert "TRUNCATE" not in upper
    assert "CREATE WAREHOUSE" not in upper
    assert "EMAIL" not in upper
    assert "HASHED_PASSWORD" not in upper
    assert "REVIEW_TEXT" not in upper
    assert "INSERT OVERWRITE" in load
    assert "LIMITATION" in load
    assert "orphan_rows" in checks
    assert "null_natural_keys" in checks
    assert "reviews_with_unknown_order" in checks


def test_star_tables_are_not_in_the_snapshot_catalog() -> None:
    for spec in STAR_TABLES:
        assert spec.table not in DATASETS_BY_TABLE
        assert spec.table in STAR_BY_TABLE
    assert "customers.parquet" in EXCLUDED_FILES
    assert "reviews.parquet" in EXCLUDED_FILES
    snapshot_sql = Path(__file__).resolve().parents[1] / "warehouse" / "snowflake" / "sql" / "analytics_tables.sql"
    text = snapshot_sql.read_text(encoding="utf-8")
    assert "DIM_CUSTOMER" not in text
    assert "FACT_ORDERS" not in text
    for statement in setup_statements("FOODPULSE", "ANALYTICS"):
        assert "DIM_DATE" not in statement


def test_column_types_use_supported_snowflake_types() -> None:
    allowed = {"VARCHAR", "NUMBER", "FLOAT", "TIMESTAMP_TZ", "BOOLEAN", "DATE"}
    for spec in STAR_TABLES:
        types = {column.snowflake_type for column in spec.dataset.columns}
        assert types <= allowed
        assert spec.dataset.columns[0].snowflake_type == "NUMBER"


def test_dry_run_does_not_connect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path)
    monkeypatch.setattr("warehouse.snowflake.connection.connect", lambda _config: (_ for _ in ()).throw(AssertionError("connect")))
    monkeypatch.setattr("warehouse.snowflake.run_star.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("warehouse.snowflake.run_star.load_config", lambda: _config())
    assert main(["--processed-dir", str(tmp_path), "--dry-run"]) == 0
    assert main(["--processed-dir", str(tmp_path)]) == 0
    assert main(["--dry-run", "--execute", "--processed-dir", str(tmp_path)]) == 1


def test_repeatable_execute_overwrites(tmp_path: Path) -> None:
    _world(tmp_path)
    first = _Cursor()
    second = _Cursor()
    publish_star(_config(), tmp_path, connector=lambda _config: _Connection(first))
    publish_star(_config(), tmp_path, connector=lambda _config: _Connection(second))
    for cursor in (first, second):
        overwrites = [statement for statement in cursor.statements if statement.startswith("INSERT OVERWRITE INTO FOODPULSE.ANALYTICS.FACT_ORDERS")]
        appends = [statement for statement in cursor.statements if statement.startswith("INSERT INTO FOODPULSE.ANALYTICS.FACT_ORDERS ")]
        assert len(overwrites) == 1
        assert appends == []
        assert any("DIM_CUSTOMER" in statement and statement.startswith("CREATE TABLE IF NOT EXISTS") for statement in cursor.statements)
    assert SECRET_PASSWORD not in str(first.statements)
    plans, _built = build_star_plan(tmp_path)
    assert [plan.table for plan in plans] == [spec.table for spec in STAR_TABLES]
    assert plans[-2].rows == 2
