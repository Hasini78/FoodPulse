"""Build one item basket per completed order.

A basket is the set of distinct food-item IDs on that order. Quantity is
presence only: a repeated line or a quantity above one does not raise
support. Item names are attached for display and are never the mining key,
because the same name can belong to more than one item.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

COMPLETED_STATUS = "completed"


@dataclass
class BasketBuild:
    """Transactions and the counts used to explain who entered mining."""

    transactions: list[list[str]]
    restaurant_ids: list[str]
    order_ids: list[str]
    item_names: dict[str, str]
    stats: dict[str, object] = field(default_factory=dict)


def build_baskets(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    food_items: pd.DataFrame,
) -> BasketBuild:
    """Return distinct-item baskets for completed orders.

    The transaction key is ``(restaurant_id, order_id)``. Order ids in the
    current extract are globally unique, but the composite key keeps two
    restaurants apart if an order id were ever reused.

    Counting:
    - ``source_orders`` is the number of order rows read.
    - ``eligible_completed_orders`` is the number of distinct
      ``(restaurant_id, order_id)`` keys whose status is ``completed``
      after rows with a missing id or restaurant id are removed.
    - ``valid_transactions`` is the number of those completed orders that
      contain at least one valid food item.
    - ``distinct_items`` is the number of food-item ids inside valid baskets.
    - Excluded rows are counted once, in the category that rejected them.
    """
    _require_columns(orders, {"id", "restaurant_id", "status"}, "orders")
    _require_columns(order_items, {"order_id", "food_item_id"}, "order_items")
    _require_columns(food_items, {"id", "restaurant_id", "name"}, "food_items")

    excluded: dict[str, int] = {
        "orders_missing_id": 0,
        "orders_missing_restaurant_id": 0,
        "duplicate_order_keys": 0,
        "orders_not_completed": 0,
        "order_items_missing_order_id": 0,
        "order_items_missing_food_item_id": 0,
        "order_items_invalid_quantity": 0,
        "order_items_unknown_order": 0,
        "order_items_not_on_completed_order": 0,
        "order_items_unknown_food": 0,
        "order_items_restaurant_mismatch": 0,
        "duplicate_items_within_order": 0,
        "completed_orders_without_valid_items": 0,
        "food_items_missing_name": 0,
    }
    source_orders = int(len(orders))
    source_order_item_rows = int(len(order_items))

    order_records: dict[tuple[str, str], str] = {}
    orders_by_id: dict[str, list[tuple[str, str]]] = {}
    for row in orders.itertuples(index=False):
        order_id = _id_token(getattr(row, "id"))
        restaurant_id = _id_token(getattr(row, "restaurant_id"))
        if order_id is None:
            excluded["orders_missing_id"] += 1
            continue
        if restaurant_id is None:
            excluded["orders_missing_restaurant_id"] += 1
            continue
        status = _status(getattr(row, "status"))
        key = (restaurant_id, order_id)
        if key in order_records:
            excluded["duplicate_order_keys"] += 1
            continue
        order_records[key] = status
        orders_by_id.setdefault(order_id, []).append(key)

    completed_keys = {
        key for key, status in order_records.items() if status == COMPLETED_STATUS
    }
    excluded["orders_not_completed"] = len(order_records) - len(completed_keys)

    catalog: dict[str, tuple[str, str]] = {}
    for row in food_items.itertuples(index=False):
        item_id = _id_token(getattr(row, "id"))
        restaurant_id = _id_token(getattr(row, "restaurant_id"))
        if item_id is None or restaurant_id is None:
            continue
        name = getattr(row, "name")
        if pd.isna(name) or str(name).strip() == "":
            catalog[item_id] = (restaurant_id, "")
        else:
            catalog[item_id] = (restaurant_id, str(name).strip())

    baskets: dict[tuple[str, str], set[str]] = {key: set() for key in completed_keys}
    has_quantity = "quantity" in order_items.columns
    for row in order_items.itertuples(index=False):
        order_id = _id_token(getattr(row, "order_id"))
        item_id = _id_token(getattr(row, "food_item_id"))
        if order_id is None:
            excluded["order_items_missing_order_id"] += 1
            continue
        if item_id is None:
            excluded["order_items_missing_food_item_id"] += 1
            continue
        if has_quantity and not _positive_quantity(getattr(row, "quantity")):
            excluded["order_items_invalid_quantity"] += 1
            continue
        candidates = orders_by_id.get(order_id)
        if not candidates:
            excluded["order_items_unknown_order"] += 1
            continue
        food = catalog.get(item_id)
        if food is None:
            excluded["order_items_unknown_food"] += 1
            continue
        food_restaurant, _name = food
        matched = [
            key
            for key in candidates
            if key[0] == food_restaurant and key in completed_keys
        ]
        if not matched:
            completed_same_id = [key for key in candidates if key in completed_keys]
            if completed_same_id:
                excluded["order_items_restaurant_mismatch"] += 1
            else:
                excluded["order_items_not_on_completed_order"] += 1
            continue
        target = matched[0]
        if item_id in baskets[target]:
            excluded["duplicate_items_within_order"] += 1
            continue
        baskets[target].add(item_id)

    transactions: list[list[str]] = []
    restaurant_ids: list[str] = []
    order_ids: list[str] = []
    used_names: dict[str, str] = {}
    missing_names = 0
    for key in sorted(completed_keys, key=_key_sort):
        items = baskets[key]
        if not items:
            excluded["completed_orders_without_valid_items"] += 1
            continue
        ordered_items = sorted(items, key=_item_sort)
        for item_id in ordered_items:
            _restaurant, name = catalog[item_id]
            used_names[item_id] = name
            if name == "":
                missing_names += 1
        transactions.append(ordered_items)
        restaurant_ids.append(key[0])
        order_ids.append(key[1])
    excluded["food_items_missing_name"] = missing_names

    stats: dict[str, object] = {
        "source_orders": source_orders,
        "source_order_item_rows": source_order_item_rows,
        "eligible_completed_orders": len(completed_keys),
        "valid_transactions": len(transactions),
        "distinct_items": len(used_names),
        "excluded_records": excluded,
        "counting": {
            "source_orders": "Order rows in the input, including invalid and non-completed rows.",
            "eligible_completed_orders": (
                "Distinct (restaurant_id, order_id) keys with status completed "
                "after dropping rows that lack an id or restaurant id."
            ),
            "valid_transactions": (
                "Eligible completed orders that contain at least one food item "
                "with a known id, a positive quantity when quantity is present, "
                "and a restaurant id matching the order."
            ),
            "distinct_items": "Unique food-item ids present in valid transactions.",
            "duplicate_items_within_order": (
                "Extra rows of an item already in that order. They are not extra support."
            ),
            "transaction_key": (
                "(restaurant_id, order_id). Items are never taken from another order "
                "or from a food item that belongs to another restaurant."
            ),
        },
    }
    return BasketBuild(
        transactions=transactions,
        restaurant_ids=restaurant_ids,
        order_ids=order_ids,
        item_names=used_names,
        stats=stats,
    )


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _id_token(value: object) -> str | None:
    """Stable id text. Whole numbers stay integers so 10 and 10.0 match."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def _status(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value).strip().lower()


def _positive_quantity(value: object) -> bool:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _key_sort(key: tuple[str, str]) -> tuple[int, str, int, str]:
    return (_numeric(key[0]), key[0], _numeric(key[1]), key[1])


def _item_sort(item_id: str) -> tuple[int, str]:
    return (_numeric(item_id), item_id)


def _numeric(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 10**18
