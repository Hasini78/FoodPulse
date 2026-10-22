"""PostgreSQL discovery adapter tests. They never write to live foodpulse."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db.session import Base
from app.models import Customer, FoodItem, Location, Order, OrderItem, Restaurant
from app.services import analytics_service, discovery_operational, discovery_service
from app.services.discovery_operational import SOURCE_ENV
from test_discovery import _world
from test_discovery_parquet_golden import (
    GOLDEN_CASE_IDS,
    _live_case,
    _load_golden,
    _require_processed_snapshot,
)

COMPLETED = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _reset_operational() -> None:
    discovery_operational.set_session_factory(None)
    discovery_operational.reset_frames()
    yield
    discovery_operational.set_session_factory(None)
    discovery_operational.reset_frames()


def _sqlite_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _enable_postgres(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    monkeypatch.setenv(SOURCE_ENV, "postgres")
    discovery_operational.set_session_factory(factory)
    discovery_operational.reset_frames()
    analytics_service._CACHE.clear()


def test_unset_and_unknown_flags_use_parquet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    monkeypatch.delenv(SOURCE_ENV, raising=False)

    def forbidden() -> None:
        raise AssertionError("operational session should not open when the source is parquet")

    discovery_operational.set_session_factory(forbidden)
    assert discovery_operational.resolve_source() == "parquet"
    payload = discovery_service.discovery("1")
    assert payload["source"] == "processed_parquet"
    assert [item["id"] for item in next(s for s in payload["sections"] if s["id"] == "picked_for_you")["items"]] == ["11", "21"]

    monkeypatch.setenv(SOURCE_ENV, "snowflake")
    assert discovery_operational.resolve_source() == "parquet"
    monkeypatch.setenv(SOURCE_ENV, " ")
    assert discovery_operational.resolve_source() == "parquet"
    monkeypatch.setenv(SOURCE_ENV, "POSTGRES")
    assert discovery_operational.resolve_source() == "postgres"


def test_postgres_failure_falls_back_to_parquet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    monkeypatch.setenv(SOURCE_ENV, "postgres")

    def boom():
        raise RuntimeError("unavailable")

    discovery_operational.set_session_factory(boom)
    payload = discovery_service.discovery("1")
    assert payload["source"] == "processed_parquet"
    picked = next(section for section in payload["sections"] if section["id"] == "picked_for_you")
    assert [item["id"] for item in picked["items"]] == ["11", "21"]


def test_completed_status_is_not_trimmed_and_quantity_is_not_summed(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, factory = _sqlite_factory()
    db = factory()
    db.add(Location(id=1, city="Pune", state="MH", country="India"))
    db.add(Restaurant(id=1, name="North", cuisine_type="Thai", location_id=1))
    db.add(Customer(id=1, first_name="A", last_name="B", email="a@example.com"))
    db.add(FoodItem(id=10, restaurant_id=1, name="Pad Thai", category="Main", price=Decimal("12.50")))
    db.add(FoodItem(id=11, restaurant_id=1, name="Pad Thai", category="Main", price=Decimal("9.00")))
    db.flush()
    db.add_all(
        [
            Order(id=1, customer_id=1, restaurant_id=1, total_amount=1, status="completed", order_date=COMPLETED),
            Order(id=2, customer_id=1, restaurant_id=1, total_amount=1, status="Completed", order_date=COMPLETED),
            Order(id=3, customer_id=1, restaurant_id=1, total_amount=1, status="completed ", order_date=COMPLETED),
            Order(id=4, customer_id=1, restaurant_id=1, total_amount=1, status="cancelled", order_date=COMPLETED),
        ]
    )
    db.add_all(
        [
            OrderItem(id=1, order_id=1, food_item_id=10, quantity=9, unit_price=Decimal("1"), subtotal=Decimal("9")),
            OrderItem(id=2, order_id=2, food_item_id=10, quantity=4, unit_price=Decimal("1"), subtotal=Decimal("4")),
            OrderItem(id=3, order_id=3, food_item_id=10, quantity=7, unit_price=Decimal("1"), subtotal=Decimal("7")),
            OrderItem(id=4, order_id=1, food_item_id=11, quantity=1, unit_price=Decimal("1"), subtotal=Decimal("1")),
        ]
    )
    db.commit()
    db.close()
    _enable_postgres(monkeypatch, factory)
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(Path("missing-processed-dir")))
    frames = discovery_operational.operational_frames()
    assert frames is not None
    counts = discovery_service._completed_item_counts([])
    assert counts["10"] == 2
    assert counts.get("11") == 1
    assert 9 not in counts.values()
    catalog = discovery_service._catalog([])
    assert set(catalog["foods"]) == {"10", "11"}
    assert catalog["foods"]["10"]["name"] == catalog["foods"]["11"]["name"] == "Pad Thai"
    engine.dispose()


def test_missing_parents_nulls_and_read_only_selects(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, factory = _sqlite_factory()
    db = factory()
    db.add(Restaurant(id=1, name="Orphan", cuisine_type="Thai", location_id=99))
    db.add(FoodItem(id=5, restaurant_id=1, name="Soup", category="Starter", price=Decimal("3")))
    db.add(Customer(id=1, first_name="A", last_name="B", email="a@example.com"))
    db.add(Order(id=8, customer_id=1, restaurant_id=1, total_amount=1, status="completed", order_date=COMPLETED))
    db.add(OrderItem(id=80, order_id=8, food_item_id=5, quantity=1, unit_price=Decimal("3"), subtotal=Decimal("3")))
    db.add(OrderItem(id=81, order_id=8, food_item_id=99, quantity=2, unit_price=Decimal("3"), subtotal=Decimal("6")))
    db.commit()
    db.close()

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    _enable_postgres(monkeypatch, factory)
    frames = discovery_operational.operational_frames()
    event.remove(engine, "before_cursor_execute", capture)
    assert frames is not None
    catalog = discovery_service._catalog([])
    assert catalog["foods"]["5"]["cuisine"] == "Thai"
    assert catalog["foods"]["5"]["city"] is None
    counts = discovery_service._completed_item_counts([])
    assert counts["5"] == 1
    assert counts["99"] == 1
    joined = " ".join(statements).upper()
    assert "SELECT" in joined
    for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
        assert verb not in joined
    engine.dispose()


def _int(value: object) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return int(value)


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value)
    return default if text == "nan" else text


def _seed_processed_sqlite(processed: Path, factory) -> None:
    db = factory()
    locations = pd.read_parquet(processed / "locations.parquet")
    restaurants = pd.read_parquet(processed / "restaurants.parquet")
    foods = pd.read_parquet(processed / "food_items.parquet")
    customers = pd.read_parquet(processed / "customers.parquet")
    orders = pd.read_parquet(processed / "orders.parquet")
    items = pd.read_parquet(processed / "order_items.parquet")
    location_rows = []
    for row in locations.to_dict("records"):
        identifier = _int(row.get("id"))
        if identifier is None:
            continue
        location_rows.append(
            {
                "id": identifier,
                "city": _text(row.get("city"), "Unknown"),
                "state": _text(row.get("state"), "Unknown"),
                "country": _text(row.get("country"), "India"),
            }
        )
    restaurant_rows = []
    for row in restaurants.to_dict("records"):
        identifier = _int(row.get("id"))
        location_id = _int(row.get("location_id"))
        if identifier is None or location_id is None:
            continue
        restaurant_rows.append(
            {
                "id": identifier,
                "name": _text(row.get("name"), "Unknown"),
                "cuisine_type": _text(row.get("cuisine_type"), "Unknown"),
                "location_id": location_id,
            }
        )
    customer_rows = []
    for row in customers.to_dict("records"):
        identifier = _int(row.get("id"))
        if identifier is None:
            continue
        customer_rows.append(
            {
                "id": identifier,
                "first_name": _text(row.get("first_name"), "Sample"),
                "last_name": _text(row.get("last_name"), "Customer"),
                "email": _text(row.get("email"), f"customer{identifier}@example.com"),
            }
        )
    food_rows = []
    for row in foods.to_dict("records"):
        identifier = _int(row.get("id"))
        restaurant_id = _int(row.get("restaurant_id"))
        if identifier is None or restaurant_id is None:
            continue
        price = row.get("price")
        try:
            amount = Decimal("0") if price is None or pd.isna(price) else Decimal(str(price))
        except Exception:
            amount = Decimal("0")
        food_rows.append(
            {
                "id": identifier,
                "restaurant_id": restaurant_id,
                "name": _text(row.get("name"), "Unknown"),
                "category": _text(row.get("category"), "Unknown"),
                "price": amount,
            }
        )
    order_rows = []
    for row in orders.to_dict("records"):
        identifier = _int(row.get("id"))
        customer_id = _int(row.get("customer_id"))
        restaurant_id = _int(row.get("restaurant_id"))
        if identifier is None or customer_id is None or restaurant_id is None:
            continue
        stamp = row.get("order_date")
        if stamp is None or (hasattr(pd, "isna") and pd.isna(stamp)):
            order_date = COMPLETED
        else:
            order_date = pd.Timestamp(stamp).to_pydatetime()
            if order_date.tzinfo is None:
                order_date = order_date.replace(tzinfo=timezone.utc)
        total = row.get("total_amount")
        try:
            amount = Decimal("0") if total is None or pd.isna(total) else Decimal(str(total))
        except Exception:
            amount = Decimal("0")
        status_value = row.get("status")
        if status_value is None or (isinstance(status_value, float) and pd.isna(status_value)):
            status_value = ""
        else:
            status_value = str(status_value)
        order_rows.append(
            {
                "id": identifier,
                "customer_id": customer_id,
                "restaurant_id": restaurant_id,
                "total_amount": amount,
                "status": status_value,
                "order_date": order_date,
            }
        )
    item_rows = []
    for row in items.to_dict("records"):
        identifier = _int(row.get("id"))
        order_id = _int(row.get("order_id"))
        food_item_id = _int(row.get("food_item_id"))
        if order_id is None or food_item_id is None:
            continue
        quantity = _int(row.get("quantity")) or 1
        unit = row.get("unit_price")
        subtotal = row.get("subtotal")
        try:
            unit_price = Decimal("0") if unit is None or pd.isna(unit) else Decimal(str(unit))
        except Exception:
            unit_price = Decimal("0")
        try:
            line_total = Decimal("0") if subtotal is None or pd.isna(subtotal) else Decimal(str(subtotal))
        except Exception:
            line_total = Decimal("0")
        mapping = {
            "order_id": order_id,
            "food_item_id": food_item_id,
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": line_total,
        }
        if identifier is not None:
            mapping["id"] = identifier
        item_rows.append(mapping)
    if location_rows:
        db.execute(insert(Location), location_rows)
    if restaurant_rows:
        db.execute(insert(Restaurant), restaurant_rows)
    if customer_rows:
        db.execute(insert(Customer), customer_rows)
    if food_rows:
        db.execute(insert(FoodItem), food_rows)
    if order_rows:
        db.execute(insert(Order), order_rows)
    if item_rows:
        db.execute(insert(OrderItem), item_rows)
    db.commit()
    db.close()


@pytest.fixture(scope="module")
def processed_sqlite():
    processed = _require_processed_snapshot()
    if not (processed / "customers.parquet").is_file() or not (processed / "locations.parquet").is_file():
        pytest.skip("processed catalog parents are not present")
    engine, factory = _sqlite_factory()
    _seed_processed_sqlite(processed, factory)
    yield processed, factory
    engine.dispose()


@pytest.mark.parametrize("case_id", GOLDEN_CASE_IDS)
def test_sqlite_adapter_matches_parquet_goldens(
    processed_sqlite,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
) -> None:
    processed, factory = processed_sqlite
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(processed))
    _enable_postgres(monkeypatch, factory)
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(processed))
    golden = _load_golden()
    expected = next(item["snapshot"] for item in golden["cases"] if item["id"] == case_id)
    request = expected["request"]
    actual = _live_case(request["customer_id"], request["cuisine"], request["category"])
    assert actual["source"] == "processed_parquet"
    assert actual["history"] == expected["history"]
    assert actual["applied"] == expected["applied"]
    assert actual["persistence"] == expected["persistence"]
    for got, want in zip(actual["sections"], expected["sections"], strict=True):
        assert got["id"] == want["id"]
        assert got["item_ids"] == want["item_ids"]
        assert got["scope"] == want["scope"]
        assert got["fallback_kind"] == want["fallback_kind"]
        assert got["empty_kind"] == want["empty_kind"]
        assert got["metric"] == want["metric"]
        assert got["explanation_kind"] == want["explanation_kind"]
        assert got["explanation_fallback"] == want["explanation_fallback"]
        assert got["first_item_reason"] == want["first_item_reason"]
        assert got["unfiltered_count"] == want["unfiltered_count"]
        assert got["available_cuisines"] == want["available_cuisines"]
        if got["id"] != "frequently_bought_together":
            continue
        for got_item, want_item in zip(got["items"], want["items"], strict=True):
            assert got_item["id"] == want_item["id"]
            assert got_item["support_count"] == want_item["support_count"]
            for field in ("lift", "confidence", "support"):
                assert got_item.get(field) == pytest.approx(want_item[field])
