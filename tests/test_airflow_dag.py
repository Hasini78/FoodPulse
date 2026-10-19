"""Structure tests for the Airflow pipeline. They do not start a scheduler."""

from __future__ import annotations

import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

DAGS = Path(__file__).resolve().parents[1] / "airflow" / "dags"
sys.path.insert(0, str(DAGS))

import foodpulse_flow as flow
from etl.transform.dataset_specs import DATASET_ORDER


def test_sample_files_match_the_transform_contract() -> None:
    assert flow.SAMPLE_FILES == tuple(f"{name}.csv" for name in DATASET_ORDER)


def test_dependency_order_respects_real_inputs() -> None:
    assert flow.DEPENDENCIES["etl_features"] == ("check_inputs",)
    assert flow.DEPENDENCIES["sentiment"] == ("etl_features",)
    assert flow.DEPENDENCIES["association"] == ("etl_features",)
    assert flow.DEPENDENCIES["forecasting"] == ("etl_features",)
    assert flow.DEPENDENCIES["clustering"] == ("sentiment",)
    assert flow.DEPENDENCIES["churn"] == ("sentiment",)
    assert flow.DEPENDENCIES["recommendations"] == ("association", "sentiment")
    assert "etl_features" not in flow.DEPENDENCIES["spark_features"]
    assert flow.DEPENDENCIES["spark_features"] == ("sentiment",)
    for upstream in ("clustering", "churn", "recommendations", "forecasting"):
        assert upstream in flow.DEPENDENCIES["snowflake_load"]
    assert "spark_features" in flow.DEPENDENCIES["validate_outputs"]
    assert "snowflake_load" in flow.DEPENDENCIES["validate_outputs"]
    assert set(flow.DEPENDENCIES) == {
        "check_inputs",
        "etl_features",
        "sentiment",
        "association",
        "forecasting",
        "clustering",
        "churn",
        "recommendations",
        "spark_features",
        "snowflake_load",
        "validate_outputs",
    }


def test_reference_date_and_missing_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(flow.REFERENCE_DATE_ENV, raising=False)
    assert flow.reference_date() == "2026-10-11"
    monkeypatch.setenv(flow.REFERENCE_DATE_ENV, "11-10-2026")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        flow.reference_date()
    monkeypatch.setenv(flow.REFERENCE_DATE_ENV, "2026-10-11")
    sample = tmp_path / "data" / "sample"
    sample.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="locations.csv"):
        flow.check_inputs(tmp_path)
    for name in flow.SAMPLE_FILES:
        (sample / name).write_text("id\n", encoding="utf-8")
    result = flow.check_inputs(tmp_path)
    assert result["reference_date"] == "2026-10-11"


def test_commands_do_not_enable_optional_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(flow.PYTHON_ENV, "python-under-test")
    monkeypatch.setenv(flow.REFERENCE_DATE_ENV, "2026-10-11")
    etl = flow.etl_command(tmp_path)
    assert "etl.pipelines.run_transform" in etl
    assert "--reference-date" in etl
    assert "USE_SPARK" not in etl
    sentiment = flow.sentiment_command(tmp_path)
    assert "--persist" not in sentiment
    assert flow.snowflake_command(tmp_path)[-1] == "--dry-run"
    monkeypatch.setenv(flow.SNOWFLAKE_EXECUTE_FLAG, "1")
    assert flow.snowflake_command(tmp_path)[-1] == "--execute"
    spark = flow.spark_command(tmp_path)
    assert spark[1].endswith("feature_aggregations.py")
    assert any("spark_features" in part for part in spark)


def test_spark_and_snowflake_skip_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(flow.SPARK_FLAG, raising=False)
    monkeypatch.delenv(flow.SNOWFLAKE_FLAG, raising=False)
    monkeypatch.setenv(flow.SNOWFLAKE_EXECUTE_FLAG, "1")
    with pytest.raises(flow.SkipStep, match="FOODPULSE_SPARK"):
        flow.run_spark(tmp_path)
    with pytest.raises(flow.SkipStep, match="FOODPULSE_SNOWFLAKE_LOAD"):
        flow.run_snowflake(tmp_path)


def test_enabled_snowflake_is_dry_run_and_failures_propagate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(command, cwd, env, check):
        calls.append((command, "USE_SPARK" in env))
        assert cwd == tmp_path
        assert check is False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(flow.subprocess, "run", fake_run)
    monkeypatch.setenv(flow.SNOWFLAKE_FLAG, "1")
    monkeypatch.delenv(flow.SNOWFLAKE_EXECUTE_FLAG, raising=False)
    monkeypatch.setenv("USE_SPARK", "1")
    flow.run_snowflake(tmp_path)
    assert calls[-1][0][-1] == "--dry-run"
    assert "--execute" not in calls[-1][0]

    def fail(command, cwd, env, check):
        assert "USE_SPARK" not in env
        return subprocess.CompletedProcess(command, 3)

    monkeypatch.setattr(flow.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="exit code 3"):
        flow.run_etl(tmp_path)


def test_output_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="orders.parquet"):
        flow.validate_outputs(tmp_path)
    for name in flow.REQUIRED_OUTPUTS:
        (processed / name).write_bytes(b"")
    monkeypatch.delenv(flow.SPARK_FLAG, raising=False)
    assert flow.validate_outputs(tmp_path)["spark_required"] == 0
    monkeypatch.setenv(flow.SPARK_FLAG, "yes")
    with pytest.raises(FileNotFoundError, match="spark_features/customer_features.parquet"):
        flow.validate_outputs(tmp_path)
    spark_dir = processed / "spark_features"
    spark_dir.mkdir()
    for name in flow.SPARK_OUTPUTS:
        (spark_dir / name).write_bytes(b"")
    assert flow.validate_outputs(tmp_path)["spark_required"] == 1


def test_dag_file_declares_the_same_tasks_and_manual_schedule() -> None:
    source = (DAGS / "foodpulse_pipeline.py").read_text(encoding="utf-8")
    assert "schedule=None" in source
    assert "TriggerRule.ALL_DONE" in source
    assert "AirflowSkipException" in source
    for task_id in flow.DEPENDENCIES:
        assert f'task_id="{task_id}"' in source
    assert "lambda" not in source


def test_airflow_image_does_not_install_the_full_project_requirements() -> None:
    dockerfile = (DAGS.parent / "Dockerfile").read_text(encoding="utf-8")
    image_requirements = (DAGS.parent / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "airflow/requirements.txt" in dockerfile
    assert "COPY --chown=airflow:root requirements.txt" not in dockerfile
    requirement_lines = [
        line.strip()
        for line in image_requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not any(line.startswith("pyspark") for line in requirement_lines)
    for package in ("pandas", "pyarrow", "scikit-learn", "mlxtend", "matplotlib", "vadersentiment", "python-dotenv"):
        assert package in image_requirements


def test_airflow_compose_shares_task_logs_without_touching_metadata_volume() -> None:
    compose = (DAGS.parents[1] / "docker-compose.airflow.yml").read_text(encoding="utf-8")
    assert compose.count("foodpulse_airflow_pg:") == 2
    assert "foodpulse_airflow_logs:/opt/airflow/logs" in compose
    assert "hostname: foodpulse-airflow-scheduler" in compose
    assert "AIRFLOW__WEBSERVER__WEB_SERVER_WORKER_TIMEOUT" in compose


def test_dag_imports_when_apache_airflow_is_installed() -> None:
    installed = Path(sysconfig.get_path("purelib")) / "airflow" / "__init__.py"
    if not installed.is_file():
        pytest.skip("apache-airflow is not installed in this interpreter")
    dag_path = DAGS / "foodpulse_pipeline.py"
    completed = subprocess.run(
        [sys.executable, "-c", "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))", str(dag_path)],
        check=False,
    )
    assert completed.returncode == 0
