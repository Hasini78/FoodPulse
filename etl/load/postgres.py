"""Load operational Parquet rows into the existing PostgreSQL tables.

Dry-run validates files only. Execute upserts by primary key and never deletes.
Locations are loaded first because restaurants require ``location_id``.
Food items follow restaurants. Order items follow orders and food items.
Users and customer activity are not part of this load.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy.engine.url import make_url

ALLOWED_DATABASES = {"foodpulse"}
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}
ALLOWED_BACKENDS = {"postgresql", "postgres"}
REASON_LIMIT = 20


@dataclass(frozen=True)
class FieldSpec:
    """One model column mapped from a Parquet column of the same name."""

    name: str
    kind: str
    required: bool = True
    max_length: int | None = None


@dataclass(frozen=True)
class TableSpec:
    """One operational table and the parents it must see first."""

    name: str
    filename: str
    model_name: str
    fields: tuple[FieldSpec, ...]
    parents: tuple[tuple[str, str], ...] = ()
    optional_parents: tuple[tuple[str, str], ...] = ()
    unique: tuple[str, ...] = ()


@dataclass
class TableSummary:
    """Counts for one table."""

    table: str
    prepared: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    rejected: int = 0
    reasons: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        if len(self.reasons) < REASON_LIMIT:
            self.reasons.append(message)


TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        "locations",
        "locations.parquet",
        "Location",
        (
            FieldSpec("id", "int"),
            FieldSpec("city", "text", max_length=100),
            FieldSpec("state", "text", max_length=100),
            FieldSpec("country", "text", max_length=100),
            FieldSpec("postal_code", "text", required=False, max_length=20),
            FieldSpec("latitude", "float", required=False),
            FieldSpec("longitude", "float", required=False),
            FieldSpec("created_at", "datetime"),
        ),
    ),
    TableSpec(
        "restaurants",
        "restaurants.parquet",
        "Restaurant",
        (
            FieldSpec("id", "int"),
            FieldSpec("name", "text", max_length=255),
            FieldSpec("cuisine_type", "text", max_length=100),
            FieldSpec("description", "text", required=False),
            FieldSpec("phone", "text", required=False, max_length=50),
            FieldSpec("email", "text", required=False, max_length=255),
            FieldSpec("location_id", "int"),
            FieldSpec("is_active", "bool"),
            FieldSpec("created_at", "datetime"),
        ),
        parents=(("location_id", "locations"),),
    ),
    TableSpec(
        "food_items",
        "food_items.parquet",
        "FoodItem",
        (
            FieldSpec("id", "int"),
            FieldSpec("restaurant_id", "int"),
            FieldSpec("name", "text", max_length=255),
            FieldSpec("category", "text", max_length=100),
            FieldSpec("description", "text", required=False),
            FieldSpec("price", "decimal"),
            FieldSpec("is_available", "bool"),
            FieldSpec("created_at", "datetime"),
        ),
        parents=(("restaurant_id", "restaurants"),),
    ),
    TableSpec(
        "customers",
        "customers.parquet",
        "Customer",
        (
            FieldSpec("id", "int"),
            FieldSpec("first_name", "text", max_length=100),
            FieldSpec("last_name", "text", max_length=100),
            FieldSpec("email", "text", max_length=255),
            FieldSpec("phone", "text", required=False, max_length=50),
            FieldSpec("city", "text", required=False, max_length=100),
            FieldSpec("date_of_birth", "date", required=False),
            FieldSpec("gender", "text", required=False, max_length=20),
            FieldSpec("created_at", "datetime"),
        ),
        unique=("email",),
    ),
    TableSpec(
        "orders",
        "orders.parquet",
        "Order",
        (
            FieldSpec("id", "int"),
            FieldSpec("customer_id", "int"),
            FieldSpec("restaurant_id", "int"),
            FieldSpec("total_amount", "decimal"),
            FieldSpec("discount_used", "decimal"),
            FieldSpec("status", "text", max_length=50),
            FieldSpec("order_date", "datetime"),
            FieldSpec("created_at", "datetime"),
        ),
        parents=(("customer_id", "customers"), ("restaurant_id", "restaurants")),
    ),
    TableSpec(
        "order_items",
        "order_items.parquet",
        "OrderItem",
        (
            FieldSpec("id", "int"),
            FieldSpec("order_id", "int"),
            FieldSpec("food_item_id", "int"),
            FieldSpec("quantity", "int"),
            FieldSpec("unit_price", "decimal"),
            FieldSpec("subtotal", "decimal"),
        ),
        parents=(("order_id", "orders"), ("food_item_id", "food_items")),
    ),
    TableSpec(
        "reviews",
        "reviews.parquet",
        "Review",
        (
            FieldSpec("id", "int"),
            FieldSpec("customer_id", "int"),
            FieldSpec("restaurant_id", "int"),
            FieldSpec("order_id", "int", required=False),
            FieldSpec("rating", "rating"),
            FieldSpec("review_text", "text"),
            FieldSpec("created_at", "datetime"),
        ),
        parents=(("customer_id", "customers"), ("restaurant_id", "restaurants")),
        optional_parents=(("order_id", "orders"),),
    ),
)

TABLES_BY_NAME = {spec.name: spec for spec in TABLES}


def verify_target(database_url: str) -> str:
    """Return the database name, or raise if this is not the local FoodPulse database."""
    parsed = make_url(database_url)
    backend = parsed.get_backend_name()
    if backend not in ALLOWED_BACKENDS:
        raise ValueError("Live load requires PostgreSQL")
    database = (parsed.database or "").strip().lower()
    if database not in ALLOWED_DATABASES:
        raise ValueError("Refusing to load: the database name is not the local FoodPulse database")
    host = (parsed.host or "").strip().lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError("Refusing to load: the host is not a local FoodPulse database")
    return database


def build_plan(processed_dir: Path) -> dict[str, object]:
    """Validate Parquet files. Does not open PostgreSQL."""
    keys: dict[str, set[int]] = {}
    rows: dict[str, list[dict[str, object]]] = {}
    summaries: dict[str, TableSummary] = {}
    unique_seen: dict[str, dict[str, set[object]]] = {}
    restaurant_of: dict[str, dict[int, int]] = {"food_items": {}, "orders": {}}
    for spec in TABLES:
        path = processed_dir / spec.filename
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
        frame = pd.read_parquet(path)
        missing = [field.name for field in spec.fields if field.required and field.name not in frame.columns]
        if missing:
            raise ValueError(f"{spec.filename} is missing required columns: {', '.join(missing)}")
        summary = TableSummary(spec.name)
        prepared: list[dict[str, object]] = []
        seen_ids: set[int] = set()
        unique_seen[spec.name] = {column: set() for column in spec.unique}
        for record in frame.to_dict("records"):
            payload, error = _row(record, spec)
            if error:
                summary.rejected += 1
                summary.note(error)
                continue
            identifier = int(payload["id"])
            if identifier in seen_ids:
                summary.skipped += 1
                summary.note(f"duplicate id {identifier}")
                continue
            unique_error = _unique_conflict(payload, spec, unique_seen[spec.name])
            if unique_error:
                summary.rejected += 1
                summary.note(unique_error)
                continue
            parent_error = _parent_error(payload, spec.parents, keys)
            if parent_error:
                summary.skipped += 1
                summary.note(parent_error)
                continue
            offering_error = _offering_restaurant_error(payload, spec.name, restaurant_of)
            if offering_error:
                summary.skipped += 1
                summary.note(offering_error)
                continue
            for column, parent in spec.optional_parents:
                value = payload.get(column)
                if value is not None and int(value) not in keys.get(parent, set()):
                    payload[column] = None
                    summary.note(f"{column} {value} is not in {parent}; stored as empty")
            seen_ids.add(identifier)
            if spec.name in restaurant_of and "restaurant_id" in payload:
                restaurant_of[spec.name][identifier] = int(payload["restaurant_id"])
            for column in spec.unique:
                unique_seen[spec.name][column].add(payload[column])
            prepared.append(payload)
        keys[spec.name] = seen_ids
        rows[spec.name] = prepared
        summary.prepared = len(prepared)
        summaries[spec.name] = summary
    return {"rows": rows, "summaries": summaries, "source": "processed_parquet"}


def apply_plan(session, plan: dict[str, object], models: dict[str, type]) -> dict[str, TableSummary]:
    """Upsert prepared rows in one transaction. Never deletes."""
    summaries: dict[str, TableSummary] = {
        name: TableSummary(name, prepared=item.prepared, skipped=item.skipped, rejected=item.rejected, reasons=list(item.reasons))
        for name, item in plan["summaries"].items()
    }
    try:
        for spec in TABLES:
            model = models[spec.model_name]
            summary = summaries[spec.name]
            for payload in plan["rows"][spec.name]:
                current = session.get(model, payload["id"])
                if current is None:
                    session.add(model(**payload))
                    summary.inserted += 1
                else:
                    for key, value in payload.items():
                        if key != "id":
                            setattr(current, key, value)
                    summary.updated += 1
            session.flush()
        _reset_sequences(session, models)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return summaries


def report(summaries: dict[str, TableSummary], dry_run: bool) -> list[dict[str, object]]:
    """JSON-ready load summary."""
    items = []
    for spec in TABLES:
        item = summaries[spec.name]
        items.append(
            {
                "table": item.table,
                "prepared": item.prepared,
                "inserted": 0 if dry_run else item.inserted,
                "updated": 0 if dry_run else item.updated,
                "skipped": item.skipped,
                "rejected": item.rejected,
                "dry_run": dry_run,
                "reasons": item.reasons,
            }
        )
    return items


def _row(record: dict[str, object], spec: TableSpec) -> tuple[dict[str, object] | None, str | None]:
    payload: dict[str, object] = {}
    for field in spec.fields:
        value, error = _value(record.get(field.name), field)
        if error:
            return None, f"{spec.name} id={record.get('id')}: {error}"
        payload[field.name] = value
    return payload, None


def _value(raw: object, field: FieldSpec) -> tuple[object, str | None]:
    if _missing(raw):
        if field.required:
            return None, f"{field.name} is required"
        return None, None
    try:
        if field.kind == "int":
            number = float(raw)
            if not float(number).is_integer() or number < 1:
                return None, f"{field.name} is not a positive whole number"
            return int(number), None
        if field.kind == "rating":
            number = float(raw)
            if not number.is_integer() or number < 1 or number > 5:
                return None, f"{field.name} must be a whole number from 1 to 5"
            return int(number), None
        if field.kind == "float":
            return float(raw), None
        if field.kind == "decimal":
            return Decimal(str(raw)).quantize(Decimal("0.01")), None
        if field.kind == "bool":
            if isinstance(raw, str):
                lowered = raw.strip().lower()
                if lowered in {"true", "1", "yes"}:
                    return True, None
                if lowered in {"false", "0", "no"}:
                    return False, None
                return None, f"{field.name} is not boolean"
            return bool(raw), None
        if field.kind == "datetime":
            stamp = pd.to_datetime(raw, utc=True, errors="coerce")
            if pd.isna(stamp):
                return None, f"{field.name} is not a timestamp"
            return stamp.to_pydatetime(), None
        if field.kind == "date":
            stamp = pd.to_datetime(raw, errors="coerce")
            if pd.isna(stamp):
                return None, f"{field.name} is not a date"
            parsed = stamp.date() if hasattr(stamp, "date") else stamp
            return parsed if isinstance(parsed, date) else None, None
        text = str(raw).strip()
        if not text:
            if field.required:
                return None, f"{field.name} is required"
            return None, None
        if field.max_length is not None and len(text) > field.max_length:
            return None, f"{field.name} exceeds {field.max_length} characters"
        if field.name == "email" and "@" not in text:
            return None, "email is invalid"
        return text, None
    except (TypeError, ValueError, InvalidOperation):
        return None, f"{field.name} has an invalid type"


def _unique_conflict(payload: dict[str, object], spec: TableSpec, seen: dict[str, set[object]]) -> str | None:
    for column in spec.unique:
        value = payload.get(column)
        if value is not None and value in seen[column]:
            return f"duplicate {column} {value}"
    return None


def _parent_error(payload: dict[str, object], parents: tuple[tuple[str, str], ...], keys: dict[str, set[int]]) -> str | None:
    for column, parent in parents:
        value = payload.get(column)
        if value is None or int(value) not in keys.get(parent, set()):
            return f"{column} {value} is not in {parent}"
    return None


def _offering_restaurant_error(
    payload: dict[str, object],
    table: str,
    restaurant_of: dict[str, dict[int, int]],
) -> str | None:
    """Skip order lines whose food offering is not on the order's restaurant."""
    if table != "order_items":
        return None
    food_id = payload.get("food_item_id")
    order_id = payload.get("order_id")
    if food_id is None or order_id is None:
        return f"order_item {payload.get('id')}: food restaurant None does not match order restaurant None"
    food_rest = restaurant_of.get("food_items", {}).get(int(food_id))
    order_rest = restaurant_of.get("orders", {}).get(int(order_id))
    if food_rest is None or order_rest is None or food_rest != order_rest:
        return (
            f"order_item {payload.get('id')}: food restaurant {food_rest} does not match "
            f"order restaurant {order_rest}"
        )
    return None


def _missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return False
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, bool) else False


def _reset_sequences(session, models: dict[str, type]) -> None:
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    for spec in TABLES:
        table = models[spec.model_name].__tablename__
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
        )
