"""Read-only food-item and order-item APIs over an in-memory SQLite session."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.api import food_items, order_items
from app.db.session import Base, get_db
from app.models import Customer, FoodItem, Location, Order, OrderItem, Restaurant


def _client_with_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    application = FastAPI()
    application.include_router(food_items.router)
    application.include_router(order_items.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides[get_db] = override_get_db
    return TestClient(application), session_factory


def _seed(session_factory) -> None:
    db = session_factory()
    try:
        db.add(Location(id=1, city="Pune", state="MH", country="India"))
        db.add(Location(id=2, city="Mumbai", state="MH", country="India"))
        db.flush()
        db.add(Restaurant(id=1, name="North", cuisine_type="Thai", location_id=1))
        db.add(Restaurant(id=2, name="South", cuisine_type="Indian", location_id=2))
        db.add(Customer(id=1, first_name="A", last_name="B", email="a@example.com"))
        db.flush()
        db.add_all(
            [
                FoodItem(
                    id=10,
                    restaurant_id=1,
                    name="Pad Thai",
                    category="Main",
                    description="noodles",
                    price=Decimal("12.50"),
                    is_available=True,
                ),
                FoodItem(
                    id=11,
                    restaurant_id=1,
                    name="Spring Roll",
                    category="Starter",
                    price=Decimal("6.00"),
                    is_available=True,
                ),
                FoodItem(
                    id=12,
                    restaurant_id=2,
                    name="Pad Thai",
                    category="Main",
                    price=Decimal("11.00"),
                    is_available=False,
                ),
            ]
        )
        db.add_all(
            [
                Order(
                    id=100,
                    customer_id=1,
                    restaurant_id=1,
                    total_amount=Decimal("25.00"),
                    discount_used=Decimal("0.00"),
                    status="completed",
                    order_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
                ),
                Order(
                    id=200,
                    customer_id=1,
                    restaurant_id=2,
                    total_amount=Decimal("11.00"),
                    discount_used=Decimal("0.00"),
                    status="completed",
                    order_date=datetime(2026, 10, 2, tzinfo=timezone.utc),
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                OrderItem(
                    id=1001,
                    order_id=100,
                    food_item_id=10,
                    quantity=2,
                    unit_price=Decimal("12.50"),
                    subtotal=Decimal("25.00"),
                ),
                OrderItem(
                    id=1002,
                    order_id=100,
                    food_item_id=11,
                    quantity=1,
                    unit_price=Decimal("6.00"),
                    subtotal=Decimal("6.00"),
                ),
                OrderItem(
                    id=2001,
                    order_id=200,
                    food_item_id=12,
                    quantity=1,
                    unit_price=Decimal("11.00"),
                    subtotal=Decimal("11.00"),
                ),
                OrderItem(
                    id=3001,
                    order_id=100,
                    food_item_id=12,
                    quantity=1,
                    unit_price=Decimal("11.00"),
                    subtotal=Decimal("11.00"),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_food_items_pagination_filter_order_and_get() -> None:
    client, sessions = _client_with_db()
    _seed(sessions)

    empty_page = client.get("/food-items", params={"skip": 0, "limit": 50, "restaurant_id": 9})
    assert empty_page.status_code == 200
    assert empty_page.json() == {"total": 0, "items": []}

    page = client.get("/food-items", params={"skip": 0, "limit": 2})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [10, 11]

    rest = client.get("/food-items", params={"skip": 2, "limit": 2})
    assert [item["id"] for item in rest.json()["items"]] == [12]
    assert rest.json()["total"] == 3

    filtered = client.get("/food-items", params={"restaurant_id": 1, "category": "Main"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    item = filtered.json()["items"][0]
    assert item["id"] == 10
    assert item["name"] == "Pad Thai"
    assert item["restaurant_id"] == 1
    assert item["price"] == 12.5
    assert item["is_available"] is True
    assert "created_at" in item

    names = client.get("/food-items", params={"category": "Main"}).json()["items"]
    assert [row["id"] for row in names] == [10, 12]
    assert [row["name"] for row in names] == ["Pad Thai", "Pad Thai"]

    found = client.get("/food-items/11")
    assert found.status_code == 200
    assert found.json()["id"] == 11
    assert found.json()["category"] == "Starter"

    missing = client.get("/food-items/999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Food item 999 not found"


def test_food_items_reject_invalid_inputs() -> None:
    client, _sessions = _client_with_db()
    assert client.get("/food-items", params={"skip": -1}).status_code == 422
    assert client.get("/food-items", params={"limit": 0}).status_code == 422
    assert client.get("/food-items", params={"limit": 201}).status_code == 422
    assert client.get("/food-items", params={"restaurant_id": 0}).status_code == 422
    assert client.get("/food-items", params={"category": ""}).status_code == 422
    assert client.get("/food-items/not-an-id").status_code == 422


def test_food_items_empty_catalog() -> None:
    client, _sessions = _client_with_db()
    response = client.get("/food-items")
    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_order_items_filters_pagination_and_fk_safe_restaurant_join() -> None:
    client, sessions = _client_with_db()
    _seed(sessions)

    listing = client.get("/order-items", params={"skip": 0, "limit": 2})
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 4
    assert [item["id"] for item in body["items"]] == [1001, 1002]
    assert set(body["items"][0]) == {
        "id",
        "order_id",
        "food_item_id",
        "quantity",
        "unit_price",
        "subtotal",
    }
    assert "email" not in body["items"][0]
    assert "customer_id" not in body["items"][0]
    assert body["items"][0]["quantity"] == 2
    assert body["items"][0]["unit_price"] == 12.5
    assert body["items"][0]["subtotal"] == 25.0

    by_order = client.get("/order-items", params={"order_id": 200})
    assert by_order.json()["total"] == 1
    assert by_order.json()["items"][0]["id"] == 2001

    by_food = client.get("/order-items", params={"food_item_id": 11})
    assert by_food.json()["total"] == 1
    assert by_food.json()["items"][0]["id"] == 1002

    matched = client.get("/order-items", params={"restaurant_id": 1})
    assert matched.status_code == 200
    assert [item["id"] for item in matched.json()["items"]] == [1001, 1002]
    assert matched.json()["total"] == 2

    none = client.get("/order-items", params={"order_id": 999})
    assert none.json() == {"total": 0, "items": []}


def test_order_items_reject_invalid_inputs() -> None:
    client, _sessions = _client_with_db()
    assert client.get("/order-items", params={"skip": -1}).status_code == 422
    assert client.get("/order-items", params={"limit": 201}).status_code == 422
    assert client.get("/order-items", params={"order_id": 0}).status_code == 422
    assert client.get("/order-items", params={"food_item_id": 0}).status_code == 422
    assert client.get("/order-items", params={"restaurant_id": 0}).status_code == 422
