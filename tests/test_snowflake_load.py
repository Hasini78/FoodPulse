"""Local tests for the Snowflake load plan. No credentials and no network."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from warehouse.snowflake.catalog import DATASETS, EXCLUDED_FILES
from warehouse.snowflake.config import SnowflakeConfig, redact
from warehouse.snowflake.connection import CONTEXT_SQL, connection_arguments
from warehouse.snowflake.ddl import session_statements, setup_statements, table_statement
from warehouse.snowflake.load import build_plan, publish
from warehouse.snowflake.run_load import main

SECRET_PASSWORD = "snowflake-password-should-not-leak"
SECRET_ACCOUNT = "account-locator.should-not-leak.snowflakecomputing.com"


def _config() -> SnowflakeConfig:
    return SnowflakeConfig(
        account=SECRET_ACCOUNT,
        user="loader",
        password=SECRET_PASSWORD,
        warehouse="FOODPULSE_WH",
        database="FOODPULSE",
        schema="ANALYTICS",
        role=None,
    )


def _write(directory: Path, filename: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(directory / filename, index=False)


def _minimal_frames() -> dict[str, pd.DataFrame]:
    sentiment_counts = {
        "review_count": [1],
        "positive_count": [1],
        "negative_count": [0],
        "neutral_count": [0],
        "invalid_count": [0],
        "mean_score": [0.5],
    }
    summary_measures = {
        "mean_recency_days": [1.0],
        "median_recency_days": [1.0],
        "mean_order_frequency": [1.0],
        "median_order_frequency": [1.0],
        "mean_total_spend": [1.0],
        "median_total_spend": [1.0],
        "mean_avg_order_value": [1.0],
        "median_avg_order_value": [1.0],
        "mean_avg_discount": [1.0],
        "median_avg_discount": [1.0],
        "mean_avg_rating": [1.0],
        "median_avg_rating": [1.0],
        "mean_avg_sentiment_score": [1.0],
        "median_avg_sentiment_score": [1.0],
    }
    return {
        "review_sentiment.parquet": pd.DataFrame(
            {
                "review_id": pd.Series([10], dtype="Int64"),
                "overall_sentiment": ["positive"],
                "overall_score": [0.8],
                "food_sent": ["positive"],
                "service_sent": ["not mentioned"],
                "ambience_sent": ["not mentioned"],
                "price_sent": [pd.NA],
                "analyzed_at": [pd.Timestamp("2026-10-11T00:00:00Z")],
            }
        ),
        "sentiment_by_restaurant.parquet": pd.DataFrame({"restaurant_id": [1], **sentiment_counts}),
        "sentiment_by_city.parquet": pd.DataFrame({"city": ["Austin"], **sentiment_counts}),
        "sentiment_by_cuisine.parquet": pd.DataFrame({"cuisine_type": ["Thai"], **sentiment_counts}),
        "sentiment_by_month.parquet": pd.DataFrame({"month": ["2026-10"], **sentiment_counts}),
        "customer_segments.parquet": pd.DataFrame({"customer_id": [1], "cluster_id": [0], "segment_label": ["high-value loyal"]}),
        "customer_segment_summary.parquet": pd.DataFrame({"cluster_id": [0], "segment_label": ["high-value loyal"], "count": [1], "percent": [1.0], **summary_measures}),
        "association_frequent_itemsets.parquet": pd.DataFrame(
            {"item_ids": ["1"], "item_names": ["Soup"], "itemset_size": [1], "support_count": [2], "support": [0.1], "restaurant_scope": ["all"]}
        ),
        "association_rules.parquet": pd.DataFrame(
            {
                "antecedent_ids": ["1"],
                "antecedent_names": ["Soup"],
                "consequent_ids": ["2"],
                "consequent_names": ["Salad"],
                "support_count": [2],
                "support": [0.1],
                "confidence": [0.5],
                "lift": [1.2],
                "leverage": [0.01],
                "conviction": [pd.NA],
                "restaurant_scope": ["all"],
            }
        ),
        "customer_churn_risk.parquet": pd.DataFrame(
            {
                "customer_id": [1],
                "inactivity_days": [10],
                "observation_days": [100],
                "order_frequency": [2],
                "total_spend": [20.0],
                "avg_order_value": [10.0],
                "avg_discount": [0.0],
                "discount_usage_rate": [0.0],
                "avg_rating": [float("nan")],
                "review_frequency": [0],
                "avg_sentiment_score": [pd.NA],
                "mean_purchase_gap_days": [5.0],
                "purchase_gap_std_days": [pd.NA],
                "recent_order_count": [1],
                "prior_order_count": [1],
                "risk_score": [pd.NA],
                "risk_category": ["insufficient_history"],
                "reason_codes": [""],
            }
        ),
        "customer_churn_summary.parquet": pd.DataFrame(
            {
                "risk_category": ["active"],
                "customer_count": [1],
                "share": [1.0],
                "median_inactivity_days": [10.0],
                "median_order_frequency": [2.0],
                "median_total_spend": [20.0],
                "median_avg_order_value": [10.0],
                "median_avg_rating": [pd.NA],
                "median_avg_sentiment_score": [pd.NA],
            }
        ),
        "food_recommendations.parquet": pd.DataFrame(
            {
                "customer_id": ["1"],
                "food_item_id": ["2"],
                "restaurant_id": ["1"],
                "recommendation_score": [0.5],
                "rank": [1],
                "reason": ["general pick for limited history"],
            }
        ),
        "restaurant_recommendations.parquet": pd.DataFrame(
            {"customer_id": ["1"], "restaurant_id": ["1"], "recommendation_score": [0.4], "rank": [1], "reason": ["highly rated restaurant"]}
        ),
        "demand_forecasts.parquet": pd.DataFrame(
            {
                "level": ["restaurant"],
                "restaurant_id": ["1"],
                "food_item_id": [pd.NA],
                "forecast_date": [pd.Timestamp("2026-10-12T00:00:00Z")],
                "horizon_step": [1],
                "horizon": [7],
                "aggregation": ["daily"],
                "model_name": ["ridge"],
                "predicted_demand": [0.0],
                "forecast_role": ["forward"],
                "evaluation_mae": [0.1],
                "evaluation_rmse": [0.2],
                "evaluation_wape": [pd.NA],
            }
        ),
        "customer_features.parquet": pd.DataFrame(
            {
                "customer_id": pd.Series([10], dtype="Int64"),
                "recency_days": [3],
                "order_frequency": [2],
                "total_spend": [15.0],
                "avg_order_value": [7.5],
                "avg_rating": pd.Series([pd.NA], dtype="Float64"),
                "review_frequency": [0],
                "discount_usage_rate": pd.Series([pd.NA], dtype="Float64"),
                "feature_reference_date": ["2026-10-11"],
            }
        ),
        "restaurant_features.parquet": pd.DataFrame(
            {
                "restaurant_id": [1],
                "avg_rating": [4.0],
                "rolling_avg_rating": [pd.NA],
                "review_volume": [1],
                "order_volume": [1],
                "complaint_count": [0],
                "sentiment_label": pd.Series([pd.NA], dtype="string"),
                "sentiment_score": pd.Series([pd.NA], dtype="Float64"),
                "feature_reference_date": ["2026-10-11"],
            }
        ),
    }


def _populate(directory: Path) -> None:
    for filename, frame in _minimal_frames().items():
        _write(directory, filename, frame)


class _Cursor:
    def __init__(self, fail_on: str | None = None) -> None:
        self.statements: list[str] = []
        self.batches: list[list[tuple]] = []
        self.staged = 0
        self.fail_on = fail_on
        self._row = None

    def execute(self, statement: str, _params=None) -> None:
        self.statements.append(statement)
        if "CREATE OR REPLACE TEMPORARY" in statement:
            self.staged = 0
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError(f"boom {SECRET_PASSWORD} {SECRET_ACCOUNT}")
        if statement == "SHOW PARAMETERS LIKE 'AUTOCOMMIT'":
            self._row = ("AUTOCOMMIT", "false")
        elif statement == "SELECT CURRENT_WAREHOUSE()":
            self._row = ("FOODPULSE_WH",)
        elif statement.startswith("SELECT COUNT(*)"):
            self._row = (self.staged,)

    def executemany(self, statement: str, rows) -> None:
        self.statements.append(statement)
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError(f"staging failed {SECRET_PASSWORD}")
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
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_obj

    def autocommit(self, _value: bool) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_dry_run_does_not_connect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _populate(tmp_path)
    monkeypatch.setattr("warehouse.snowflake.connection.connect", lambda _config: (_ for _ in ()).throw(AssertionError("connect")))
    assert main(["--processed-dir", str(tmp_path), "--dry-run"]) == 0
    assert main(["--processed-dir", str(tmp_path)]) == 0


def test_missing_file_and_column_fail_before_connection(tmp_path: Path) -> None:
    calls = {"count": 0}

    def _connect(_config):
        calls["count"] += 1
        raise AssertionError("connect")

    with pytest.raises(FileNotFoundError):
        build_plan(tmp_path)
    _populate(tmp_path)
    frame = pd.read_parquet(tmp_path / "review_sentiment.parquet")
    frame.drop(columns=["overall_score"]).to_parquet(tmp_path / "review_sentiment.parquet", index=False)
    with pytest.raises(ValueError, match="overall_score"):
        build_plan(tmp_path, ["REVIEW_SENTIMENT"])
    assert calls["count"] == 0
    assert main(["--processed-dir", str(tmp_path / "missing"), "--execute"]) == 1


def test_default_plan_excludes_pii_and_history(tmp_path: Path) -> None:
    _populate(tmp_path)
    for name in EXCLUDED_FILES:
        _write(tmp_path, name, pd.DataFrame({"secret": ["x"]}))
    _write(tmp_path / "association_restaurant_run" if False else tmp_path, "ignored.parquet", pd.DataFrame({"x": [1]}))
    plans = build_plan(tmp_path)
    filenames = {plan.path.name for plan in plans}
    assert filenames == {dataset.filename for dataset in DATASETS}
    assert set(EXCLUDED_FILES).isdisjoint(filenames)
    assert "association_restaurant_run" not in filenames


def test_nullable_values_and_identifier_types(tmp_path: Path) -> None:
    _populate(tmp_path)
    cursor = _Cursor()
    connection = _Connection(cursor)
    publish(_config(), tmp_path, ["CUSTOMER_FEATURES", "ASSOCIATION_RULES", "DEMAND_FORECASTS"], connector=lambda _config: connection)
    inserted = [statement for statement in cursor.statements if statement.startswith("INSERT INTO")]
    assert inserted
    feature_batch = next(rows for rows in cursor.batches if rows and rows[0][0] == "10")
    assert feature_batch[0][5] is None
    assert feature_batch[0][7] is None
    rule_batch = next(rows for rows in cursor.batches if rows and rows[0][0] == "1")
    assert rule_batch[0][9] is None
    forecast_batch = next(rows for rows in cursor.batches if rows and rows[0][0] == "restaurant")
    assert forecast_batch[0][2] is None
    assert forecast_batch[0][12] is None
    assert isinstance(forecast_batch[0][3], datetime)


def test_credentials_are_removed_from_connection_errors(tmp_path: Path) -> None:
    _populate(tmp_path)

    def _connect(config: SnowflakeConfig):
        raise RuntimeError(f"login failed for {config.password} at https://{config.account}")

    with pytest.raises(RuntimeError) as caught:
        publish(_config(), tmp_path, connector=_connect)
    message = str(caught.value)
    assert SECRET_PASSWORD not in message
    assert SECRET_ACCOUNT not in message
    assert "[redacted]" in message


def test_redact_replaces_each_secret() -> None:
    assert SECRET_PASSWORD not in redact(f"see {SECRET_PASSWORD}", (SECRET_PASSWORD,))


def test_repeated_loads_overwrite_instead_of_appending(tmp_path: Path) -> None:
    _populate(tmp_path)
    first = _Cursor()
    second = _Cursor()
    publish(_config(), tmp_path, ["FOOD_RECOMMENDATIONS"], connector=lambda _config: _Connection(first))
    publish(_config(), tmp_path, ["FOOD_RECOMMENDATIONS"], connector=lambda _config: _Connection(second))
    for cursor in (first, second):
        overwrites = [statement for statement in cursor.statements if statement.startswith("INSERT OVERWRITE INTO FOODPULSE.ANALYTICS.FOOD_RECOMMENDATIONS")]
        appends = [statement for statement in cursor.statements if statement.startswith("INSERT INTO FOODPULSE.ANALYTICS.FOOD_RECOMMENDATIONS ")]
        assert len(overwrites) == 1
        assert appends == []


def test_failed_staging_does_not_publish(tmp_path: Path) -> None:
    _populate(tmp_path)
    cursor = _Cursor(fail_on="INSERT INTO")
    connection = _Connection(cursor)
    with pytest.raises(RuntimeError, match="not published"):
        publish(_config(), tmp_path, ["CUSTOMER_SEGMENTS"], connector=lambda _config: connection)
    assert not any(statement.startswith("INSERT OVERWRITE") for statement in cursor.statements)
    assert connection.rollbacks == 1
    assert SECRET_PASSWORD not in str(cursor.statements)


def test_reviewed_sql_matches_the_non_destructive_setup() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "warehouse" / "snowflake" / "sql" / "analytics_tables.sql"
    text = sql_path.read_text(encoding="utf-8")
    for statement in session_statements("FOODPULSE_WH", "FOODPULSE", "ANALYTICS"):
        assert statement in text
    for statement in setup_statements("FOODPULSE", "ANALYTICS"):
        assert statement in text
    upper = text.upper()
    assert "DROP " not in upper
    assert "TRUNCATE " not in upper
    assert "CREATE OR REPLACE" not in upper
    assert "CREATE WAREHOUSE" not in upper
    assert "USERS" not in upper
    assert "HASHED_PASSWORD" not in upper


def test_connection_does_not_require_database_or_schema() -> None:
    arguments = connection_arguments(_config())
    assert "database" not in arguments
    assert "schema" not in arguments
    assert arguments["warehouse"] == "FOODPULSE_WH"
    assert arguments["paramstyle"] == "qmark"
    assert arguments["account"] == SECRET_ACCOUNT


def test_autocommit_failure_aborts_before_writes(tmp_path: Path) -> None:
    _populate(tmp_path)
    cursor = _Cursor()

    class _Broken:
        def __init__(self) -> None:
            self.closed = False

        def autocommit(self, _mode: bool) -> None:
            raise RuntimeError(f"session rejected {SECRET_PASSWORD}")

        def cursor(self) -> _Cursor:
            return cursor

        def close(self) -> None:
            self.closed = True

    broken = _Broken()
    with pytest.raises(RuntimeError, match="autocommit") as caught:
        publish(_config(), tmp_path, ["CUSTOMER_SEGMENTS"], connector=lambda _config: broken)
    assert cursor.statements == []
    assert broken.closed is True
    assert SECRET_PASSWORD not in str(caught.value)


def test_autocommit_remaining_enabled_aborts_before_writes(tmp_path: Path) -> None:
    _populate(tmp_path)
    cursor = _Cursor()
    cursor.execute = _enabled_autocommit(cursor)
    with pytest.raises(RuntimeError, match="autocommit"):
        publish(_config(), tmp_path, ["CUSTOMER_SEGMENTS"], connector=lambda _config: _Connection(cursor))
    assert not any(statement.startswith("CREATE ") or statement.startswith("USE ") for statement in cursor.statements)


def _enabled_autocommit(cursor: _Cursor):
    original = cursor.execute

    def _execute(statement: str, _params=None) -> None:
        original(statement, _params)
        if statement == "SHOW PARAMETERS LIKE 'AUTOCOMMIT'":
            cursor._row = ("AUTOCOMMIT", "true")

    return _execute


def test_rollback_failure_keeps_a_sanitized_original_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _populate(tmp_path)
    cursor = _Cursor(fail_on="INSERT INTO")

    class _RollbackFails(_Connection):
        def rollback(self) -> None:
            raise RuntimeError(f"rollback broke {SECRET_PASSWORD} at {SECRET_ACCOUNT}")

    caplog.set_level("ERROR")
    with pytest.raises(RuntimeError, match="not published") as caught:
        publish(_config(), tmp_path, ["CUSTOMER_SEGMENTS"], connector=lambda _config: _RollbackFails(cursor))
    message = str(caught.value)
    assert "staging failed" in message
    assert SECRET_PASSWORD not in message
    assert SECRET_ACCOUNT not in message
    assert SECRET_PASSWORD not in caplog.text
    assert SECRET_ACCOUNT not in caplog.text
    assert "Rollback failed" in caplog.text


def test_selected_tables_do_not_initialize_the_others(tmp_path: Path) -> None:
    _populate(tmp_path)
    cursor = _Cursor()
    publish(_config(), tmp_path, ["CUSTOMER_SEGMENTS"], connector=lambda _config: _Connection(cursor))
    created = [statement for statement in cursor.statements if statement.startswith("CREATE TABLE")]
    assert created == [table_statement(_dataset("CUSTOMER_SEGMENTS"), "FOODPULSE", "ANALYTICS")]
    assert not any("REVIEW_SENTIMENT" in statement for statement in cursor.statements)


def _dataset(table: str):
    from warehouse.snowflake.catalog import DATASETS_BY_TABLE

    return DATASETS_BY_TABLE[table]


def test_changed_input_aborts_before_connection(tmp_path: Path) -> None:
    _populate(tmp_path)
    plans = build_plan(tmp_path, ["CUSTOMER_SEGMENTS"])
    target = tmp_path / "customer_segments.parquet"
    target.write_bytes(target.read_bytes() + b"changed")
    calls = {"count": 0}

    def _connect(_config):
        calls["count"] += 1
        raise AssertionError("connect")

    with pytest.raises(RuntimeError, match="changed after validation"):
        publish(_config(), plans=plans, connector=_connect)
    assert calls["count"] == 0
    assert target.read_bytes().endswith(b"changed")


def test_execution_loads_the_validated_records(tmp_path: Path) -> None:
    _populate(tmp_path)
    plans = build_plan(tmp_path, ["CUSTOMER_SEGMENTS"])
    cursor = _Cursor()
    publish(_config(), plans=plans, connector=lambda _config: _Connection(cursor))
    assert cursor.batches == [list(plans[0].records)]


def test_configuration_representation_hides_secrets() -> None:
    rendered = repr(_config())
    assert SECRET_PASSWORD not in rendered
    assert SECRET_ACCOUNT not in rendered
    assert "loader" not in rendered


def test_cli_rejects_unknown_tables_and_both_modes(tmp_path: Path) -> None:
    assert main(["--tables", "USERS", "--processed-dir", str(tmp_path)]) == 1
    assert main(["--dry-run", "--execute", "--processed-dir", str(tmp_path)]) == 1
    assert main(["--test-connection", "--execute"]) == 1


def _patch_connection_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("warehouse.snowflake.run_load.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("warehouse.snowflake.run_load.load_config", lambda: _config())
    monkeypatch.setattr(
        "warehouse.snowflake.run_load.build_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("loader")),
    )


def test_test_connection_prints_context_and_closes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _patch_connection_config(monkeypatch)
    cursor = _ContextCursor(("8.12.0", "FOODPULSE_WH", None, None))
    connection = _Connection(cursor)
    monkeypatch.setattr("warehouse.snowflake.run_load.connect", lambda _config: connection)
    assert main(["--test-connection"]) == 0
    assert cursor.statements == [CONTEXT_SQL]
    assert cursor.closed is True
    assert connection.closed is True
    printed = capsys.readouterr().out
    assert "version=8.12.0" in printed
    assert "warehouse=FOODPULSE_WH" in printed
    assert "database=None" in printed
    assert "schema=None" in printed
    assert SECRET_PASSWORD not in printed
    assert SECRET_ACCOUNT not in printed


def test_test_connection_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _patch_connection_config(monkeypatch)

    def _connect(config: SnowflakeConfig):
        raise RuntimeError(f"login failed for {config.password} at https://{config.account}")

    monkeypatch.setattr("warehouse.snowflake.run_load.connect", _connect)
    caplog.set_level("ERROR")
    assert main(["--test-connection"]) == 1
    assert SECRET_PASSWORD not in caplog.text
    assert SECRET_ACCOUNT not in caplog.text
    assert "[redacted]" in caplog.text


def test_test_connection_closes_when_the_query_fails(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _patch_connection_config(monkeypatch)
    cursor = _ContextCursor(failure=f"query failed for {SECRET_PASSWORD}")
    connection = _Connection(cursor)
    monkeypatch.setattr("warehouse.snowflake.run_load.connect", lambda _config: connection)
    caplog.set_level("ERROR")
    assert main(["--test-connection"]) == 1
    assert cursor.closed is True
    assert connection.closed is True
    assert SECRET_PASSWORD not in caplog.text
    assert "[redacted]" in caplog.text


class _ContextCursor:
    def __init__(self, row: tuple | None = None, failure: str | None = None) -> None:
        self.statements: list[str] = []
        self.closed = False
        self._row = row
        self._failure = failure

    def execute(self, statement: str, _params=None) -> None:
        self.statements.append(statement)
        if self._failure:
            raise RuntimeError(self._failure)

    def fetchone(self):
        return self._row

    def close(self) -> None:
        self.closed = True
