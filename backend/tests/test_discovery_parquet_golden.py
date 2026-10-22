"""Parquet discovery goldens over live data/processed.

Temporary-world tests in test_discovery.py stay the source of algorithm
checks. These cases freeze ranking identity for customers 1, 2, 8, and 9
on the current processed snapshot. They do not assert PostgreSQL parity.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services import analytics_service, discovery_service
from app.services.analytics_service import AnalyticsDataError

GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "discovery_parquet_golden.json"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

CUSTOMERS = ("1", "2", "8", "9")
FILTERS = (
    {"cuisine": None, "category": None},
    {"cuisine": "Indian", "category": None},
    {"cuisine": "Indian", "category": "Side"},
)
REQUEST = {
    "limit": 8,
    "min_support_count": 14,
    "min_confidence": 0.3,
    "min_lift": 1.0,
}
REQUIRED_FILES = (
    "food_items.parquet",
    "restaurants.parquet",
    "orders.parquet",
    "order_items.parquet",
    "food_recommendations.parquet",
    "restaurant_recommendations.parquet",
    "association_rules.parquet",
)


def _require_processed_snapshot() -> Path:
    if not PROCESSED_DIR.is_dir():
        pytest.skip("processed directory is not present")
    for name in REQUIRED_FILES:
        if not (PROCESSED_DIR / name).is_file():
            pytest.skip(f"{name} is not present")
    return PROCESSED_DIR


def project_payload(payload: dict) -> dict:
    """Keep ranking identity; drop display-only and nondeterministic fields."""
    sections = []
    for section in payload["sections"]:
        items = list(section.get("items") or [])
        first = items[0] if items else None
        projected_items = []
        for item in items:
            row = {
                "id": None if item.get("id") is None else str(item["id"]),
                "kind": item.get("kind"),
            }
            if section["id"] == "frequently_bought_together":
                row["lift"] = analytics_service._json_value(item.get("lift"))
                row["confidence"] = analytics_service._json_value(item.get("confidence"))
                row["support"] = analytics_service._json_value(item.get("support"))
                row["support_count"] = analytics_service._json_value(item.get("support_count"))
            projected_items.append(row)
        explanation = section.get("explanation") or {}
        sections.append(
            {
                "id": section["id"],
                "scope": section.get("scope"),
                "fallback_kind": section.get("fallback_kind"),
                "empty_kind": section.get("empty_kind"),
                "metric": section.get("metric"),
                "explanation_kind": explanation.get("kind"),
                "explanation_fallback": explanation.get("fallback"),
                "item_ids": [row["id"] for row in projected_items],
                "first_item_reason": None if first is None else first.get("reason"),
                "items": projected_items,
                "unfiltered_count": section.get("unfiltered_count"),
                "available_cuisines": section.get("available_cuisines"),
            }
        )
    persistence = payload.get("persistence") or {}
    return {
        "source": payload.get("source"),
        "customer_id": str(payload.get("customer_id")),
        "unavailable": list(payload.get("unavailable") or []),
        "history": payload.get("history"),
        "applied": (payload.get("filters") or {}).get("applied"),
        "persistence": {
            "save": persistence.get("save"),
            "like": persistence.get("like"),
            "dislike": persistence.get("dislike"),
        },
        "sections": sections,
    }


def _live_case(customer_id: str, cuisine: str | None, category: str | None) -> dict:
    payload = discovery_service.discovery(
        customer_id,
        limit=REQUEST["limit"],
        min_support_count=REQUEST["min_support_count"],
        min_confidence=REQUEST["min_confidence"],
        min_lift=REQUEST["min_lift"],
        cuisine=cuisine,
        category=category,
    )
    projected = project_payload(payload)
    projected["request"] = {
        "customer_id": customer_id,
        "cuisine": cuisine,
        "category": category,
        **REQUEST,
    }
    return projected


def _load_golden() -> dict:
    if not GOLDEN_PATH.is_file():
        pytest.fail(f"golden fixture is missing: {GOLDEN_PATH}")
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _case_id(customer_id: str, cuisine: str | None, category: str | None) -> str:
    cuisine_part = cuisine or "none"
    category_part = category or "none"
    return f"customer-{customer_id}-cuisine-{cuisine_part}-category-{category_part}"


GOLDEN_CASE_IDS = [_case_id(customer, spec["cuisine"], spec["category"]) for customer in CUSTOMERS for spec in FILTERS]


@pytest.fixture
def live_processed(monkeypatch: pytest.MonkeyPatch) -> Path:
    processed = _require_processed_snapshot()
    monkeypatch.delenv("FOODPULSE_PROCESSED_DIR", raising=False)
    analytics_service._CACHE.clear()
    assert analytics_service.processed_dir() == processed
    return processed


def test_golden_fixture_lists_the_twelve_live_cases() -> None:
    golden = _load_golden()
    assert golden["source"] == "processed_parquet"
    assert golden["request"] == REQUEST
    ids = [item["id"] for item in golden["cases"]]
    assert ids == GOLDEN_CASE_IDS
    assert len(ids) == 12
    assert len(set(ids)) == 12


@pytest.mark.parametrize("case_id", GOLDEN_CASE_IDS)
def test_live_parquet_discovery_matches_golden(live_processed: Path, case_id: str) -> None:
    golden = _load_golden()
    expected = next(item["snapshot"] for item in golden["cases"] if item["id"] == case_id)
    request = expected["request"]
    try:
        actual = _live_case(request["customer_id"], request["cuisine"], request["category"])
    except AnalyticsDataError as exc:
        pytest.skip(exc.message)
    assert actual["source"] == "processed_parquet"
    assert actual["unavailable"] == expected["unavailable"]
    assert actual["history"] == expected["history"]
    assert actual["applied"] == expected["applied"]
    assert actual["persistence"] == expected["persistence"]
    assert [section["id"] for section in actual["sections"]] == [section["id"] for section in expected["sections"]]
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
        assert len(got["items"]) == len(want["items"])
        for got_item, want_item in zip(got["items"], want["items"], strict=True):
            assert got_item["id"] == want_item["id"]
            assert got_item["kind"] == want_item["kind"]
            if got["id"] != "frequently_bought_together":
                continue
            assert got_item["support_count"] == want_item["support_count"]
            for field in ("lift", "confidence", "support"):
                if want_item.get(field) is None:
                    assert got_item.get(field) is None
                else:
                    assert got_item.get(field) == pytest.approx(want_item[field])
