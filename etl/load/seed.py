"""
Generate realistic FoodPulse sample data with Faker, export CSVs, and load into PostgreSQL.

Usage (from project root, with DATABASE_URL set):
    python etl/load/seed.py
    python etl/load/seed.py --csv-only
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Allow importing backend.app when run from project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from app.db.session import Base  # noqa: E402
from app.models import (  # noqa: E402
    Customer,
    CustomerActivity,
    FoodItem,
    Location,
    Order,
    OrderItem,
    Restaurant,
    Review,
    User,
)

fake = Faker()
Faker.seed(42)
random.seed(42)

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"

NUM_LOCATIONS = 20
NUM_RESTAURANTS = 50
NUM_CUSTOMERS = 500
NUM_ORDERS = 5000
NUM_REVIEWS = 3000
NUM_USERS = 5
FOOD_ITEMS_PER_RESTAURANT = (8, 15)
ORDER_ITEMS_PER_ORDER = (1, 5)
ACTIVITIES_PER_CUSTOMER = (1, 4)

CUISINES = [
    "Indian",
    "Chinese",
    "Italian",
    "Mexican",
    "Japanese",
    "Thai",
    "American",
    "Mediterranean",
    "Korean",
    "Vietnamese",
]

FOOD_CATALOG: dict[str, list[tuple[str, str, float]]] = {
    "Indian": [
        ("Butter Chicken", "Main", 320.0),
        ("Paneer Tikka", "Starter", 220.0),
        ("Biryani", "Main", 280.0),
        ("Naan", "Bread", 40.0),
        ("Dal Makhani", "Main", 200.0),
        ("Samosa", "Starter", 60.0),
        ("Mango Lassi", "Beverage", 90.0),
        ("Gulab Jamun", "Dessert", 80.0),
        ("Masala Dosa", "Main", 150.0),
        ("Chole Bhature", "Main", 180.0),
    ],
    "Chinese": [
        ("Kung Pao Chicken", "Main", 260.0),
        ("Veg Fried Rice", "Main", 180.0),
        ("Spring Rolls", "Starter", 120.0),
        ("Hot & Sour Soup", "Soup", 140.0),
        ("Hakka Noodles", "Main", 190.0),
        ("Manchurian", "Main", 210.0),
        ("Dim Sum", "Starter", 250.0),
        ("Jasmine Tea", "Beverage", 70.0),
    ],
    "Italian": [
        ("Margherita Pizza", "Main", 350.0),
        ("Pasta Carbonara", "Main", 320.0),
        ("Garlic Bread", "Starter", 110.0),
        ("Caesar Salad", "Salad", 180.0),
        ("Tiramisu", "Dessert", 160.0),
        ("Minestrone", "Soup", 140.0),
        ("Risotto", "Main", 300.0),
        ("Espresso", "Beverage", 80.0),
    ],
    "Mexican": [
        ("Chicken Tacos", "Main", 240.0),
        ("Beef Burrito", "Main", 280.0),
        ("Nachos", "Starter", 190.0),
        ("Guacamole", "Starter", 150.0),
        ("Quesadilla", "Main", 220.0),
        ("Churros", "Dessert", 120.0),
        ("Horchata", "Beverage", 90.0),
    ],
    "Japanese": [
        ("Salmon Sushi", "Main", 450.0),
        ("Ramen", "Main", 320.0),
        ("Tempura", "Starter", 260.0),
        ("Miso Soup", "Soup", 100.0),
        ("Edamame", "Starter", 120.0),
        ("Matcha Ice Cream", "Dessert", 140.0),
        ("Green Tea", "Beverage", 70.0),
    ],
    "Thai": [
        ("Pad Thai", "Main", 260.0),
        ("Green Curry", "Main", 280.0),
        ("Tom Yum Soup", "Soup", 180.0),
        ("Spring Rolls", "Starter", 130.0),
        ("Mango Sticky Rice", "Dessert", 150.0),
        ("Thai Iced Tea", "Beverage", 90.0),
    ],
    "American": [
        ("Cheeseburger", "Main", 250.0),
        ("BBQ Ribs", "Main", 420.0),
        ("French Fries", "Side", 100.0),
        ("Onion Rings", "Starter", 120.0),
        ("Mac & Cheese", "Main", 200.0),
        ("Chocolate Shake", "Beverage", 140.0),
        ("Brownie", "Dessert", 110.0),
    ],
    "Mediterranean": [
        ("Falafel Wrap", "Main", 220.0),
        ("Chicken Shawarma", "Main", 260.0),
        ("Hummus Plate", "Starter", 160.0),
        ("Greek Salad", "Salad", 180.0),
        ("Baklava", "Dessert", 130.0),
        ("Mint Lemonade", "Beverage", 80.0),
    ],
    "Korean": [
        ("Bibimbap", "Main", 300.0),
        ("Kimchi Fried Rice", "Main", 240.0),
        ("Korean Fried Chicken", "Main", 350.0),
        ("Japchae", "Main", 260.0),
        ("Tteokbokki", "Starter", 180.0),
        ("Sikhye", "Beverage", 90.0),
    ],
    "Vietnamese": [
        ("Pho Bo", "Main", 280.0),
        ("Banh Mi", "Main", 180.0),
        ("Spring Rolls", "Starter", 140.0),
        ("Bun Cha", "Main", 250.0),
        ("Vietnamese Coffee", "Beverage", 100.0),
        ("Che", "Dessert", 110.0),
    ],
}

# Review templates mixed across food / service / price for future sentiment work
POSITIVE_FOOD = [
    "The {dish} was absolutely delicious and perfectly seasoned.",
    "Loved the flavors in the {dish}; fresh ingredients throughout.",
    "Best {dish} I've had in months - rich aroma and great texture.",
    "Food quality is outstanding; the {dish} exceeded expectations.",
]
NEGATIVE_FOOD = [
    "The {dish} arrived cold and tasted bland.",
    "Disappointed with the {dish}; overcooked and under-seasoned.",
    "Food was average; {dish} lacked the promised spice and depth.",
    "The {dish} was oily and not worth ordering again.",
]
POSITIVE_SERVICE = [
    "Staff were attentive and the service was quick and friendly.",
    "Excellent hospitality - our server checked in at the right times.",
    "Smooth experience from seating to checkout; very professional team.",
    "Servers were courteous and handled our large group effortlessly.",
]
NEGATIVE_SERVICE = [
    "We waited far too long; service felt rushed and inattentive.",
    "Order mix-up and slow response from the staff ruined the evening.",
    "Service was cold and unhelpful when we asked about allergens.",
    "Long wait for seating and delayed order confirmation.",
]
POSITIVE_PRICE = [
    "Great value for money given the portion sizes.",
    "Pricing felt fair for the quality - will happily come back.",
    "Reasonable prices and a solid lunch deal.",
    "Worth every rupee; portions are generous.",
]
NEGATIVE_PRICE = [
    "Overpriced for what you get; portions were tiny.",
    "Felt nickel-and-dimed with extras; not good value.",
    "Prices have gone up without any improvement in quality.",
    "Too expensive compared to similar places nearby.",
]
NEUTRAL = [
    "Decent overall - nothing spectacular but nothing terrible either.",
    "Average experience; might visit again if nearby.",
    "Food and service were okay; still deciding if I'd recommend it.",
]

ACTIVITY_TYPES = [
    "app_login",
    "browse_menu",
    "add_to_cart",
    "place_order",
    "leave_review",
    "redeem_coupon",
    "view_restaurant",
]


def _hash_password(password: str) -> str:
    """Simple deterministic hash for seed users (not for production auth)."""
    return hashlib.sha256(password.encode()).hexdigest()


def _money(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def generate_review_text(rating: int, dish: str) -> str:
    """Build a review mixing food, service, and price angles based on rating."""
    if rating >= 4:
        pools = [POSITIVE_FOOD, POSITIVE_SERVICE, POSITIVE_PRICE]
    elif rating <= 2:
        pools = [NEGATIVE_FOOD, NEGATIVE_SERVICE, NEGATIVE_PRICE]
    else:
        pools = [NEUTRAL, POSITIVE_FOOD, NEGATIVE_PRICE]

    chosen = random.sample(pools, k=min(2, len(pools)))
    parts: list[str] = []
    for pool in chosen:
        template = random.choice(pool)
        parts.append(template.format(dish=dish))
    return " ".join(parts)


def ensure_sample_dir() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(name: str, rows: list[dict]) -> Path:
    path = SAMPLE_DIR / name
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  wrote {path} ({len(rows)} rows)")
    return path


def generate_data() -> dict[str, list[dict]]:
    """Generate all entity rows as plain dicts suitable for CSV and ORM load."""
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=365)

    locations: list[dict] = []
    for i in range(1, NUM_LOCATIONS + 1):
        locations.append(
            {
                "id": i,
                "city": fake.city(),
                "state": fake.state(),
                "country": "India",
                "postal_code": fake.postcode(),
                "latitude": float(fake.latitude()),
                "longitude": float(fake.longitude()),
                "created_at": fake.date_time_between(start_date=start_date, end_date=now, tzinfo=timezone.utc),
            }
        )

    users: list[dict] = []
    for i in range(1, NUM_USERS + 1):
        users.append(
            {
                "id": i,
                "email": f"analyst{i}@foodpulse.local",
                "full_name": fake.name(),
                "hashed_password": _hash_password("password123"),
                "is_active": True,
                "role": random.choice(["admin", "analyst", "viewer"]),
                "created_at": fake.date_time_between(start_date=start_date, end_date=now, tzinfo=timezone.utc),
            }
        )

    restaurants: list[dict] = []
    for i in range(1, NUM_RESTAURANTS + 1):
        cuisine = random.choice(CUISINES)
        restaurants.append(
            {
                "id": i,
                "name": f"{fake.company()} {random.choice(['Kitchen', 'Bistro', 'Grill', 'Cafe', 'House'])}",
                "cuisine_type": cuisine,
                "description": fake.catch_phrase(),
                "phone": fake.phone_number(),
                "email": fake.company_email(),
                "location_id": random.randint(1, NUM_LOCATIONS),
                "is_active": random.random() > 0.05,
                "created_at": fake.date_time_between(start_date=start_date, end_date=now, tzinfo=timezone.utc),
            }
        )

    food_items: list[dict] = []
    food_id = 1
    restaurant_food_ids: dict[int, list[int]] = {}
    for restaurant in restaurants:
        cuisine = restaurant["cuisine_type"]
        catalog = FOOD_CATALOG.get(cuisine, FOOD_CATALOG["Indian"])
        count = random.randint(*FOOD_ITEMS_PER_RESTAURANT)
        chosen = random.choices(catalog, k=count)
        restaurant_food_ids[restaurant["id"]] = []
        for name, category, base_price in chosen:
            price = round(base_price * random.uniform(0.85, 1.25), 2)
            food_items.append(
                {
                    "id": food_id,
                    "restaurant_id": restaurant["id"],
                    "name": name,
                    "category": category,
                    "description": fake.sentence(nb_words=8),
                    "price": price,
                    "is_available": random.random() > 0.08,
                    "created_at": restaurant["created_at"],
                }
            )
            restaurant_food_ids[restaurant["id"]].append(food_id)
            food_id += 1

    customers: list[dict] = []
    for i in range(1, NUM_CUSTOMERS + 1):
        dob = fake.date_of_birth(minimum_age=18, maximum_age=70)
        customers.append(
            {
                "id": i,
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": f"customer{i}@example.com",
                "phone": fake.phone_number(),
                "city": fake.city(),
                "date_of_birth": dob,
                "gender": random.choice(["male", "female", "other", None]),
                "created_at": fake.date_time_between(start_date=start_date, end_date=now, tzinfo=timezone.utc),
            }
        )

    food_by_id = {f["id"]: f for f in food_items}

    orders: list[dict] = []
    order_items: list[dict] = []
    order_item_id = 1
    order_meta: list[dict] = []  # track dishes for review generation

    for i in range(1, NUM_ORDERS + 1):
        restaurant = random.choice(restaurants)
        food_ids = restaurant_food_ids[restaurant["id"]]
        if not food_ids:
            continue

        customer_id = random.randint(1, NUM_CUSTOMERS)
        order_date = fake.date_time_between(start_date=start_date, end_date=now, tzinfo=timezone.utc)
        n_items = random.randint(*ORDER_ITEMS_PER_ORDER)
        selected_food_ids = random.sample(food_ids, k=min(n_items, len(food_ids)))

        subtotal = Decimal("0.00")
        dishes: list[str] = []
        for fid in selected_food_ids:
            food = food_by_id[fid]
            qty = random.randint(1, 3)
            unit_price = _money(float(food["price"]))
            line_total = unit_price * qty
            subtotal += line_total
            dishes.append(food["name"])
            order_items.append(
                {
                    "id": order_item_id,
                    "order_id": i,
                    "food_item_id": fid,
                    "quantity": qty,
                    "unit_price": float(unit_price),
                    "subtotal": float(line_total),
                }
            )
            order_item_id += 1

        discount = _money(0)
        if random.random() < 0.35:
            discount = _money(float(subtotal) * random.uniform(0.05, 0.20))

        total = max(subtotal - discount, Decimal("0.00"))
        orders.append(
            {
                "id": i,
                "customer_id": customer_id,
                "restaurant_id": restaurant["id"],
                "total_amount": float(total),
                "discount_used": float(discount),
                "status": random.choices(
                    ["completed", "cancelled", "pending"],
                    weights=[0.88, 0.07, 0.05],
                )[0],
                "order_date": order_date,
                "created_at": order_date,
            }
        )
        order_meta.append(
            {
                "order_id": i,
                "customer_id": customer_id,
                "restaurant_id": restaurant["id"],
                "dishes": dishes,
                "order_date": order_date,
            }
        )

    # Reviews: prefer tying to completed orders
    completed_meta = [
        m
        for m, o in zip(order_meta, orders)
        if o["status"] == "completed"
    ]
    random.shuffle(completed_meta)
    review_targets = completed_meta[:NUM_REVIEWS]
    # If fewer completed orders than needed, pad with random customers/restaurants
    while len(review_targets) < NUM_REVIEWS:
        r = random.choice(restaurants)
        review_targets.append(
            {
                "order_id": None,
                "customer_id": random.randint(1, NUM_CUSTOMERS),
                "restaurant_id": r["id"],
                "dishes": [random.choice(FOOD_CATALOG[r["cuisine_type"]])[0]],
                "order_date": fake.date_time_between(start_date=start_date, end_date=now, tzinfo=timezone.utc),
            }
        )

    reviews: list[dict] = []
    for i, target in enumerate(review_targets[:NUM_REVIEWS], start=1):
        # Skew ratings slightly positive (realistic review distribution)
        rating = random.choices([1, 2, 3, 4, 5], weights=[0.08, 0.12, 0.20, 0.30, 0.30])[0]
        dish = random.choice(target["dishes"]) if target["dishes"] else "meal"
        created = target["order_date"] + timedelta(hours=random.randint(1, 72))
        if created > now:
            created = now
        reviews.append(
            {
                "id": i,
                "customer_id": target["customer_id"],
                "restaurant_id": target["restaurant_id"],
                "order_id": target["order_id"],
                "rating": rating,
                "review_text": generate_review_text(rating, dish),
                "created_at": created,
            }
        )

    activities: list[dict] = []
    activity_id = 1
    for customer in customers:
        for _ in range(random.randint(*ACTIVITIES_PER_CUSTOMER)):
            activity_date = fake.date_time_between(
                start_date=customer["created_at"],
                end_date=now,
                tzinfo=timezone.utc,
            )
            activity_type = random.choice(ACTIVITY_TYPES)
            activities.append(
                {
                    "id": activity_id,
                    "customer_id": customer["id"],
                    "activity_type": activity_type,
                    "description": f"Customer {customer['id']} performed {activity_type}",
                    "activity_date": activity_date,
                    "created_at": activity_date,
                }
            )
            activity_id += 1

    return {
        "locations": locations,
        "users": users,
        "restaurants": restaurants,
        "food_items": food_items,
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
        "reviews": reviews,
        "customer_activity": activities,
    }


def export_csvs(data: dict[str, list[dict]]) -> None:
    ensure_sample_dir()
    print("Exporting CSVs to data/sample/ ...")
    for name, rows in data.items():
        save_csv(f"{name}.csv", rows)


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and configure it."
        )
    return url


def reset_and_create_schema(engine) -> None:
    print("Recreating database schema ...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def load_into_db(data: dict[str, list[dict]], session: Session) -> None:
    print("Loading data into PostgreSQL ...")

    session.add_all([Location(**row) for row in data["locations"]])
    session.flush()

    session.add_all([User(**row) for row in data["users"]])
    session.flush()

    session.add_all([Restaurant(**row) for row in data["restaurants"]])
    session.flush()

    session.add_all([FoodItem(**row) for row in data["food_items"]])
    session.flush()

    session.add_all([Customer(**row) for row in data["customers"]])
    session.flush()

    session.add_all([Order(**row) for row in data["orders"]])
    session.flush()

    session.add_all([OrderItem(**row) for row in data["order_items"]])
    session.flush()

    session.add_all([Review(**row) for row in data["reviews"]])
    session.flush()

    session.add_all([CustomerActivity(**row) for row in data["customer_activity"]])
    session.commit()

    # Reset sequences so future inserts don't collide with explicit IDs
    tables = [
        "locations",
        "users",
        "restaurants",
        "food_items",
        "customers",
        "orders",
        "order_items",
        "reviews",
        "customer_activity",
    ]
    for table in tables:
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
        )
    session.commit()
    print("Seed load complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FoodPulse sample data")
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Generate and export CSVs without loading PostgreSQL",
    )
    args = parser.parse_args()

    print("FoodPulse seed — generating sample data ...")
    data = generate_data()
    print(
        f"Generated: {len(data['restaurants'])} restaurants, "
        f"{len(data['customers'])} customers, "
        f"{len(data['orders'])} orders, "
        f"{len(data['reviews'])} reviews"
    )
    export_csvs(data)

    if args.csv_only:
        print("Done. CSVs are in data/sample/ (database load skipped).")
        return

    database_url = get_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    reset_and_create_schema(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        load_into_db(data, session)

    print("Done. CSVs are in data/sample/ and PostgreSQL is seeded.")


if __name__ == "__main__":
    main()
