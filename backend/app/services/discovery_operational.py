"""Optional PostgreSQL source for discovery catalog and order history.

Stored ranks, association rules, restaurant features, and sentiment stay on
Parquet. This module is read-only and is off unless the source flag is
``postgres``. Unknown or failed sources fall back to Parquet.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from contextlib import contextmanager
from typing import Iterator

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import FoodItem, Location, Order, OrderItem, Restaurant

logger = logging.getLogger(__name__)

SOURCE_ENV = "FOODPULSE_DISCOVERY_OPERATIONAL_SOURCE"
PARQUET_SOURCE = "parquet"
POSTGRES_SOURCE = "postgres"
SUPPORTED_SOURCES = {PARQUET_SOURCE, POSTGRES_SOURCE}

SessionFactory = Callable[[], Session]

_session_factory: SessionFactory | sessionmaker | None = None
_frames: dict[str, pd.DataFrame] | None | bool = None


def resolve_source(raw: str | None = None) -> str:
    """Return parquet unless the flag is exactly postgres (after strip/lower)."""
    value = os.environ.get(SOURCE_ENV) if raw is None else raw
    if value is None:
        return PARQUET_SOURCE
    normalized = str(value).strip().lower()
    if normalized == POSTGRES_SOURCE:
        return POSTGRES_SOURCE
    return PARQUET_SOURCE


def set_session_factory(factory: SessionFactory | sessionmaker | None) -> None:
    """Tests inject an in-memory sessionmaker. Production keeps SessionLocal."""
    global _session_factory
    _session_factory = factory


def reset_frames() -> None:
    """Drop the per-request operational cache."""
    global _frames
    _frames = None


def operational_frames() -> dict[str, pd.DataFrame] | None:
    """Load catalog and order frames from PostgreSQL, or None to use Parquet."""
    global _frames
    if _frames is False:
        return None
    if isinstance(_frames, dict):
        return _frames
    if resolve_source() != POSTGRES_SOURCE:
        _frames = False
        return None
    try:
        with _session() as session:
            loaded = load_operational_frames(session)
    except Exception as exc:
        logger.warning(
            "Discovery operational PostgreSQL source failed (%s); using Parquet",
            type(exc).__name__,
        )
        _frames = False
        return None
    _frames = loaded
    return loaded


def load_operational_frames(session: Session) -> dict[str, pd.DataFrame]:
    """Read catalog and order lines. Does not filter is_available or quantity."""
    restaurant_rows = session.execute(
        select(
            Restaurant.id,
            Restaurant.name,
            Restaurant.cuisine_type,
            Restaurant.location_id,
        ).order_by(Restaurant.id)
    ).all()
    location_rows = session.execute(select(Location.id, Location.city).order_by(Location.id)).all()
    food_rows = session.execute(
        select(
            FoodItem.id,
            FoodItem.restaurant_id,
            FoodItem.name,
            FoodItem.category,
            FoodItem.price,
        ).order_by(FoodItem.id)
    ).all()
    order_rows = session.execute(
        select(Order.id, Order.customer_id, Order.restaurant_id, Order.status).order_by(Order.id)
    ).all()
    item_rows = session.execute(select(OrderItem.order_id, OrderItem.food_item_id).order_by(OrderItem.id)).all()
    return {
        "restaurants": pd.DataFrame(
            [
                {
                    "id": row.id,
                    "name": row.name,
                    "cuisine_type": row.cuisine_type,
                    "location_id": row.location_id,
                }
                for row in restaurant_rows
            ],
            columns=["id", "name", "cuisine_type", "location_id"],
        ),
        "locations": pd.DataFrame(
            [{"id": row.id, "city": row.city} for row in location_rows],
            columns=["id", "city"],
        ),
        "foods": pd.DataFrame(
            [
                {
                    "id": row.id,
                    "restaurant_id": row.restaurant_id,
                    "name": row.name,
                    "category": row.category,
                    "price": None if row.price is None else float(row.price),
                }
                for row in food_rows
            ],
            columns=["id", "restaurant_id", "name", "category", "price"],
        ),
        "orders": pd.DataFrame(
            [
                {
                    "id": row.id,
                    "customer_id": row.customer_id,
                    "restaurant_id": row.restaurant_id,
                    "status": row.status,
                }
                for row in order_rows
            ],
            columns=["id", "customer_id", "restaurant_id", "status"],
        ),
        "items": pd.DataFrame(
            [{"order_id": row.order_id, "food_item_id": row.food_item_id} for row in item_rows],
            columns=["order_id", "food_item_id"],
        ),
    }


@contextmanager
def _session() -> Iterator[Session]:
    factory = _session_factory
    if factory is None:
        from app.db.session import SessionLocal

        factory = SessionLocal
    session = factory()
    try:
        try:
            session.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:
            pass
        yield session
        session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
