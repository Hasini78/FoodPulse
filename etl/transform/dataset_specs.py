"""Column contracts taken from the sample CSVs and SQLAlchemy models.

Dataset names match ``data/sample/<name>.csv``. Primary keys are the ``id``
columns. Foreign keys use the same column names as the ORM models.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForeignKey:
    """A column that must point at another dataset's primary key."""

    column: str
    references: str
    nullable: bool = False


@dataclass(frozen=True)
class DatasetSpec:
    """Cleaning and validation contract for one sample table."""

    name: str
    columns: tuple[str, ...]
    primary_key: str
    non_nullable: tuple[str, ...]
    integer_columns: tuple[str, ...]
    float_columns: tuple[str, ...]
    datetime_columns: tuple[str, ...]
    date_columns: tuple[str, ...]
    boolean_columns: tuple[str, ...]
    text_columns: tuple[str, ...]
    optional_nullable: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...]
    fill_zero: tuple[str, ...] = ()


DATASET_SPECS: dict[str, DatasetSpec] = {
    "locations": DatasetSpec(
        name="locations",
        columns=(
            "id",
            "city",
            "state",
            "country",
            "postal_code",
            "latitude",
            "longitude",
            "created_at",
        ),
        primary_key="id",
        non_nullable=("id", "city", "state", "country", "created_at"),
        integer_columns=("id",),
        float_columns=("latitude", "longitude"),
        datetime_columns=("created_at",),
        date_columns=(),
        boolean_columns=(),
        text_columns=("city", "state", "country", "postal_code"),
        optional_nullable=("postal_code", "latitude", "longitude"),
        foreign_keys=(),
    ),
    "users": DatasetSpec(
        name="users",
        columns=(
            "id",
            "email",
            "full_name",
            "hashed_password",
            "is_active",
            "role",
            "created_at",
        ),
        primary_key="id",
        non_nullable=(
            "id",
            "email",
            "full_name",
            "hashed_password",
            "is_active",
            "role",
            "created_at",
        ),
        integer_columns=("id",),
        float_columns=(),
        datetime_columns=("created_at",),
        date_columns=(),
        boolean_columns=("is_active",),
        text_columns=("email", "full_name", "hashed_password", "role"),
        optional_nullable=(),
        foreign_keys=(),
    ),
    "restaurants": DatasetSpec(
        name="restaurants",
        columns=(
            "id",
            "name",
            "cuisine_type",
            "description",
            "phone",
            "email",
            "location_id",
            "is_active",
            "created_at",
        ),
        primary_key="id",
        non_nullable=("id", "name", "cuisine_type", "location_id", "is_active", "created_at"),
        integer_columns=("id", "location_id"),
        float_columns=(),
        datetime_columns=("created_at",),
        date_columns=(),
        boolean_columns=("is_active",),
        text_columns=("name", "cuisine_type", "description", "phone", "email"),
        optional_nullable=("description", "phone", "email"),
        foreign_keys=(ForeignKey("location_id", "locations"),),
    ),
    "food_items": DatasetSpec(
        name="food_items",
        columns=(
            "id",
            "restaurant_id",
            "name",
            "category",
            "description",
            "price",
            "is_available",
            "created_at",
        ),
        primary_key="id",
        non_nullable=(
            "id",
            "restaurant_id",
            "name",
            "category",
            "price",
            "is_available",
            "created_at",
        ),
        integer_columns=("id", "restaurant_id"),
        float_columns=("price",),
        datetime_columns=("created_at",),
        date_columns=(),
        boolean_columns=("is_available",),
        text_columns=("name", "category", "description"),
        optional_nullable=("description",),
        foreign_keys=(ForeignKey("restaurant_id", "restaurants"),),
    ),
    "customers": DatasetSpec(
        name="customers",
        columns=(
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "city",
            "date_of_birth",
            "gender",
            "created_at",
        ),
        primary_key="id",
        non_nullable=("id", "first_name", "last_name", "email", "created_at"),
        integer_columns=("id",),
        float_columns=(),
        datetime_columns=("created_at",),
        date_columns=("date_of_birth",),
        boolean_columns=(),
        text_columns=("first_name", "last_name", "email", "phone", "city", "gender"),
        optional_nullable=("phone", "city", "date_of_birth", "gender"),
        foreign_keys=(),
    ),
    "orders": DatasetSpec(
        name="orders",
        columns=(
            "id",
            "customer_id",
            "restaurant_id",
            "total_amount",
            "discount_used",
            "status",
            "order_date",
            "created_at",
        ),
        primary_key="id",
        non_nullable=(
            "id",
            "customer_id",
            "restaurant_id",
            "total_amount",
            "discount_used",
            "status",
            "order_date",
            "created_at",
        ),
        integer_columns=("id", "customer_id", "restaurant_id"),
        float_columns=("total_amount", "discount_used"),
        datetime_columns=("order_date", "created_at"),
        date_columns=(),
        boolean_columns=(),
        text_columns=("status",),
        optional_nullable=(),
        foreign_keys=(
            ForeignKey("customer_id", "customers"),
            ForeignKey("restaurant_id", "restaurants"),
        ),
        fill_zero=("discount_used",),
    ),
    "order_items": DatasetSpec(
        name="order_items",
        columns=(
            "id",
            "order_id",
            "food_item_id",
            "quantity",
            "unit_price",
            "subtotal",
        ),
        primary_key="id",
        non_nullable=("id", "order_id", "food_item_id", "quantity", "unit_price", "subtotal"),
        integer_columns=("id", "order_id", "food_item_id", "quantity"),
        float_columns=("unit_price", "subtotal"),
        datetime_columns=(),
        date_columns=(),
        boolean_columns=(),
        text_columns=(),
        optional_nullable=(),
        foreign_keys=(
            ForeignKey("order_id", "orders"),
            ForeignKey("food_item_id", "food_items"),
        ),
    ),
    "reviews": DatasetSpec(
        name="reviews",
        columns=(
            "id",
            "customer_id",
            "restaurant_id",
            "order_id",
            "rating",
            "review_text",
            "created_at",
        ),
        primary_key="id",
        non_nullable=("id", "customer_id", "restaurant_id", "rating", "review_text", "created_at"),
        integer_columns=("id", "customer_id", "restaurant_id", "order_id", "rating"),
        float_columns=(),
        datetime_columns=("created_at",),
        date_columns=(),
        boolean_columns=(),
        text_columns=("review_text",),
        optional_nullable=("order_id",),
        foreign_keys=(
            ForeignKey("customer_id", "customers"),
            ForeignKey("restaurant_id", "restaurants"),
            ForeignKey("order_id", "orders", nullable=True),
        ),
    ),
    "customer_activity": DatasetSpec(
        name="customer_activity",
        columns=(
            "id",
            "customer_id",
            "activity_type",
            "description",
            "activity_date",
            "created_at",
        ),
        primary_key="id",
        non_nullable=("id", "customer_id", "activity_type", "activity_date", "created_at"),
        integer_columns=("id", "customer_id"),
        float_columns=(),
        datetime_columns=("activity_date", "created_at"),
        date_columns=(),
        boolean_columns=(),
        text_columns=("activity_type", "description"),
        optional_nullable=("description",),
        foreign_keys=(ForeignKey("customer_id", "customers"),),
    ),
}

DATASET_ORDER: tuple[str, ...] = tuple(DATASET_SPECS)
