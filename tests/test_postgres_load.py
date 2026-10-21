"""PostgreSQL operational loader tests. Uses SQLite; does not touch the real database."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "postgres-loader-test-key"

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import Base
from app.models.customer import Customer
from app.models.location import Location
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.review import Review
from etl.load.postgres import TableSummary, apply_plan, build_plan, report, verify_target
from etl.pipelines.run_postgres_load import main, run_load

MODELS = {
    "Location": Location,
    "Restaurant": Restaurant,
    "Customer": Customer,
    "Order": Order,
    "Review": Review,
}
PROCESSED = ROOT / "data" / "processed"


def _write(directory: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(directory / name, index=False)


def _world(directory: Path) -> None:
    _write(
        directory,
        "locations.parquet",
        pd.DataFrame(
            {
                "id": [5],
                "city": ["Pune"],
                "state": ["MH"],
                "country": ["IN"],
                "postal_code": ["411001"],
                "latitude": [18.5],
                "longitude": [73.8],
                "created_at": [pd.Timestamp("2026-01-01T00:00:00Z")],
            }
        ),
    )
    _write(
        directory,
        "restaurants.parquet",
        pd.DataFrame(
            {
                "id": [10, 11],
                "name": ["Thai House", "Missing Place"],
                "cuisine_type": ["Thai", "Indian"],
                "description": ["A", "B"],
                "phone": ["111", "222"],
                "email": ["thai@example.com", "x@example.com"],
                "location_id": [5, 99],
                "is_active": [True, True],
                "created_at": [pd.Timestamp("2026-01-01T00:00:00Z")] * 2,
            }
        ),
    )
    _write(
        directory,
        "customers.parquet",
        pd.DataFrame(
            {
                "id": [1, 1, 2, 3, 4],
                "first_name": ["Ada", "Ada", "Bob", "Bad", "Eve"],
                "last_name": ["Lee", "Lee", "Ray", "Row", "Ng"],
                "email": [
                    "ada@example.com",
                    "ada@example.com",
                    "bob@example.com",
                    "not-an-email",
                    "ada@example.com",
                ],
                "phone": ["1", "1", "2", "3", "4"],
                "city": ["Pune", "Pune", "Mumbai", "X", "Pune"],
                "date_of_birth": [pd.Timestamp("1990-01-01")] * 5,
                "gender": ["F", "F", "M", "X", "F"],
                "created_at": [pd.Timestamp("2026-01-01T00:00:00Z")] * 5,
            }
        ),
    )
    _write(
        directory,
        "orders.parquet",
        pd.DataFrame(
            {
                "id": [100, 101],
                "customer_id": [1, 9],
                "restaurant_id": [10, 10],
                "total_amount": [20.5, 9.0],
                "discount_used": [1.0, 0.0],
                "status": ["completed", "completed"],
                "order_date": [pd.Timestamp("2026-10-01T10:00:00Z")] * 2,
                "created_at": [pd.Timestamp("2026-10-01T10:00:00Z")] * 2,
                "is_total_outlier": [False, False],
                "total_amount_capped": [20.5, 9.0],
            }
        ),
    )
    _write(
        directory,
        "reviews.parquet",
        pd.DataFrame(
            {
                "id": [7, 8, 9],
                "customer_id": [1, 2, 2],
                "restaurant_id": [10, 10, 10],
                "order_id": [100, 999, 999],
                "rating": [5, 9, 4],
                "review_text": ["great", "bad-rating", "ok"],
                "created_at": [pd.Timestamp("2026-10-01T18:00:00Z")] * 3,
            }
        ),
    )


def _session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi, _connection_record):
        dbapi.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_mapping_and_foreign_key_order(tmp_path: Path) -> None:
    _world(tmp_path)
    plan = build_plan(tmp_path)
    assert [row["id"] for row in plan["rows"]["locations"]] == [5]
    assert [row["id"] for row in plan["rows"]["restaurants"]] == [10]
    assert plan["summaries"]["restaurants"].skipped == 1
    assert [row["id"] for row in plan["rows"]["customers"]] == [1, 2]
    assert plan["summaries"]["customers"].skipped == 1
    assert plan["summaries"]["customers"].rejected == 2
    assert [row["id"] for row in plan["rows"]["orders"]] == [100]
    assert plan["summaries"]["orders"].skipped == 1
    assert "is_total_outlier" not in plan["rows"]["orders"][0]
    assert [row["id"] for row in plan["rows"]["reviews"]] == [7, 9]
    assert plan["rows"]["reviews"][0]["order_id"] == 100
    assert plan["rows"]["reviews"][1]["order_id"] is None
    assert plan["summaries"]["reviews"].rejected == 1


def test_dry_run_performs_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path)
    session = _session()
    opened = []
    written = []
    monkeypatch.setattr("etl.pipelines.run_postgres_load._open_session", lambda: opened.append("open") or session)
    monkeypatch.setattr("etl.pipelines.run_postgres_load.apply_plan", lambda *args, **kwargs: written.append(args) or {})
    assert main(["--processed-dir", str(tmp_path)]) == 0
    assert main(["--processed-dir", str(tmp_path), "--dry-run"]) == 0
    assert opened == []
    assert written == []
    assert session.scalar(select(Restaurant.id)) is None
    assert main(["--dry-run", "--execute", "--processed-dir", str(tmp_path)]) == 1


def test_live_mode_requires_explicit_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path)
    monkeypatch.setattr(
        "etl.pipelines.run_postgres_load._open_session",
        lambda: (_ for _ in ()).throw(AssertionError("live session opened without --execute")),
    )
    payload = run_load(tmp_path, execute=False)
    assert all(item["dry_run"] is True and item["inserted"] == 0 for item in payload)
    assert main(["--processed-dir", str(tmp_path)]) == 0


def test_execute_upserts_and_is_repeatable(tmp_path: Path) -> None:
    _world(tmp_path)
    session = _session()
    first = run_load(tmp_path, execute=True, session_factory=lambda: session)
    by_table = {item["table"]: item for item in first}
    assert by_table["locations"]["inserted"] == 1
    assert by_table["restaurants"]["inserted"] == 1
    assert by_table["customers"]["inserted"] == 2
    assert by_table["orders"]["inserted"] == 1
    assert by_table["reviews"]["inserted"] == 2
    assert session.get(Restaurant, 10).name == "Thai House"
    assert session.get(Review, 7).rating == 5
    assert session.get(Review, 9).order_id is None
    frame = pd.read_parquet(tmp_path / "restaurants.parquet")
    frame.loc[frame["id"] == 10, "name"] = "Thai House Updated"
    frame.to_parquet(tmp_path / "restaurants.parquet", index=False)
    second = run_load(tmp_path, execute=True, session_factory=lambda: session)
    by_table = {item["table"]: item for item in second}
    assert by_table["restaurants"]["updated"] == 1
    assert by_table["restaurants"]["inserted"] == 0
    assert len(session.scalars(select(Restaurant)).all()) == 1
    assert session.get(Restaurant, 10).name == "Thai House Updated"


def test_transaction_rolls_back_on_failure(tmp_path: Path) -> None:
    _world(tmp_path)
    session = _session()
    plan = build_plan(tmp_path)
    broken = dict(MODELS)
    broken["Review"] = object
    with pytest.raises(Exception):
        apply_plan(session, plan, broken)
    assert session.get(Restaurant, 10) is None
    assert session.get(Customer, 1) is None
    assert session.get(Order, 100) is None


def test_missing_file_invalid_values_and_target(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_plan(tmp_path)
    _write(
        tmp_path,
        "locations.parquet",
        pd.DataFrame({"id": [1], "city": ["Pune"]}),
    )
    with pytest.raises(ValueError, match="missing required columns"):
        build_plan(tmp_path)
    with pytest.raises(ValueError, match="PostgreSQL"):
        verify_target("sqlite:///:memory:")
    with pytest.raises(ValueError, match="database name"):
        verify_target("postgresql://user:secret@localhost:5432/airflow")
    with pytest.raises(ValueError, match="host"):
        verify_target("postgresql://user:secret@prod.example.com:5432/foodpulse")
    assert verify_target("postgresql://user:secret@localhost:5432/foodpulse") == "foodpulse"
    summaries = {spec: TableSummary(spec, prepared=1) for spec in ("locations", "restaurants", "customers", "orders", "reviews")}
    payload = report(summaries, True)
    assert all(item["inserted"] == 0 and item["updated"] == 0 and item["dry_run"] is True for item in payload)


def test_summary_counts_match_plan(tmp_path: Path) -> None:
    _world(tmp_path)
    plan = build_plan(tmp_path)
    payload = report(plan["summaries"], dry_run=True)
    by_table = {item["table"]: item for item in payload}
    assert by_table["locations"]["prepared"] == 1
    assert by_table["restaurants"]["prepared"] == 1
    assert by_table["restaurants"]["skipped"] == 1
    assert by_table["customers"]["skipped"] == 1
    assert by_table["customers"]["rejected"] == 2
    assert by_table["orders"]["skipped"] == 1
    assert by_table["reviews"]["prepared"] == 2
    assert by_table["reviews"]["rejected"] == 1
    assert all(item["inserted"] == 0 and item["updated"] == 0 for item in payload)


@pytest.mark.skipif(not (PROCESSED / "orders.parquet").is_file(), reason="processed Parquet files are not present")
def test_real_processed_files_map_without_database() -> None:
    plan = build_plan(PROCESSED)
    payload = report(plan["summaries"], dry_run=True)
    by_table = {item["table"]: item for item in payload}
    assert by_table["locations"]["prepared"] == 20
    assert by_table["restaurants"]["prepared"] == 50
    assert by_table["customers"]["prepared"] == 500
    assert by_table["orders"]["prepared"] == 5000
    assert by_table["reviews"]["prepared"] == 3000
    assert all(item["skipped"] == 0 and item["rejected"] == 0 for item in payload)
    assert "is_total_outlier" not in plan["rows"]["orders"][0]
    assert all(item["inserted"] == 0 for item in payload)
