"""Menu inspection over injected HTML. This does not call Google Places or the public web."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services import analytics_service, menu_inspect_service


MENU_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Menu",
  "hasMenuSection": [{
    "@type": "MenuSection",
    "name": "Mains",
    "hasMenuItem": [{
      "@type": "MenuItem",
      "name": "Masala Dosa",
      "description": "Fermented rice crepe",
      "offers": {"@type": "Offer", "price": "180", "priceCurrency": "INR"}
    }]
  }]
}
</script>
<a href="/menu">Full menu</a>
</body></html>
"""

WEBSITE_NO_MENU_HTML = """
<html><body>
<h1>Spice House</h1>
<p>Call us for today's specials.</p>
<a href="/about">About</a>
</body></html>
"""

WEBSITE_MENU_LINK_HTML = """
<html><body>
<a href="https://spice.example/menu">View menu</a>
</body></html>
"""


def _write(directory: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(directory / name, index=False)


def _pages(mapping: dict[str, tuple[int, str]]) -> menu_inspect_service.FetchFn:
    def fetch(url: str) -> tuple[int, str, str]:
        if url not in mapping:
            raise menu_inspect_service.MenuInspectError("fetch_failed", f"unexpected url {url}")
        status, body = mapping[url]
        return status, url, body

    return fetch


def test_no_url_does_not_invent_a_menu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    payload = menu_inspect_service.inspect_menu()
    assert payload["status"] == "google_has_no_menu"
    assert payload["items"] == []
    assert payload["suggestions"] == []
    assert payload["used_google_places"] is False
    assert payload["foodpulse_match"]["matched"] is False
    assert "not this restaurant" in payload["notice"].lower() or "not this restaurant's menu" in payload["notice"].lower()


def test_jsonld_menu_items_become_nonpersonalized_suggestions() -> None:
    payload = menu_inspect_service.inspect_menu(
        "https://spice.example/eat",
        fetch=_pages({"https://spice.example/eat": (200, MENU_HTML)}),
    )
    assert payload["status"] == "menu_found"
    assert payload["items"][0]["name"] == "Masala Dosa"
    assert payload["items"][0]["price"] == 180.0
    assert payload["items"][0]["currency"] == "INR"
    assert payload["items"][0]["source"] == "jsonld_menuitem"
    assert payload["suggestions"][0]["personalized"] is False
    assert payload["suggestions"][0]["foodpulse_history"] is False
    assert "not a foodpulse sample" in payload["suggestions"][0]["reason"].lower()
    assert payload["used_foodpulse_history"] is False


def test_website_without_structured_menu_stays_empty() -> None:
    payload = menu_inspect_service.inspect_menu(
        "https://spice.example/",
        fetch=_pages({"https://spice.example/": (200, WEBSITE_NO_MENU_HTML)}),
    )
    assert payload["status"] == "no_structured_menu"
    assert payload["items"] == []
    assert payload["suggestions"] == []
    assert "not turned into a menu" in payload["notice"].lower()


def test_menu_link_is_followed_on_the_same_host() -> None:
    payload = menu_inspect_service.inspect_menu(
        "https://spice.example/",
        fetch=_pages(
            {
                "https://spice.example/": (200, WEBSITE_MENU_LINK_HTML),
                "https://spice.example/menu": (200, MENU_HTML),
            }
        ),
    )
    assert payload["status"] == "menu_found"
    assert [item["name"] for item in payload["items"]] == ["Masala Dosa"]


def test_google_maps_url_is_not_scraped() -> None:
    payload = menu_inspect_service.inspect_menu("https://maps.google.com/?cid=2", fetch=_pages({}))
    assert payload["status"] == "maps_listing_not_menu"
    assert payload["items"] == []


def test_localhost_is_blocked() -> None:
    payload = menu_inspect_service.inspect_menu("http://127.0.0.1/menu", fetch=_pages({}))
    assert payload["status"] == "blocked_url"
    assert payload["items"] == []


def test_fetch_failure_does_not_invent_items() -> None:
    payload = menu_inspect_service.inspect_menu(
        "https://spice.example/down",
        fetch=_pages({"https://spice.example/down": (503, "unavailable")}),
    )
    assert payload["status"] == "fetch_failed"
    assert payload["items"] == []


def test_unmatched_google_place_does_not_use_foodpulse_dishes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    _write(tmp_path, "restaurants.parquet", pd.DataFrame({"id": [1], "name": ["Spice Room"], "cuisine_type": ["Indian"]}))
    _write(
        tmp_path,
        "food_items.parquet",
        pd.DataFrame({"id": [20], "restaurant_id": [1], "name": ["Biryani"], "category": ["Main"], "price": [14.0]}),
    )
    payload = menu_inspect_service.inspect_menu(google_place_id="ChIJ-unmatched")
    assert payload["foodpulse_match"]["matched"] is False
    assert payload["foodpulse_items"] == []
    assert "name and cuisine" in payload["foodpulse_match"]["reason"].lower()


def test_exact_place_id_match_lists_sample_catalog_separately(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    _write(
        tmp_path,
        "restaurants.parquet",
        pd.DataFrame({"id": [9], "name": ["Matched Kitchen"], "google_place_id": ["ChIJ-match"]}),
    )
    _write(
        tmp_path,
        "food_items.parquet",
        pd.DataFrame({"id": [99], "restaurant_id": [9], "name": ["Idli"], "category": ["Starter"], "price": [40.0]}),
    )
    payload = menu_inspect_service.inspect_menu(google_place_id="ChIJ-match")
    assert payload["foodpulse_match"]["matched"] is True
    assert payload["foodpulse_match"]["restaurant_id"] == "9"
    assert payload["foodpulse_match"]["match_field"] == "google_place_id"
    assert payload["items"] == []
    assert payload["foodpulse_items"][0]["name"] == "Idli"
    assert payload["foodpulse_items"][0]["source"] == "foodpulse_catalog"
    assert "sample record" in payload["foodpulse_items"][0]["reason"].lower()


def test_name_collision_is_not_a_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    _write(
        tmp_path,
        "restaurants.parquet",
        pd.DataFrame({"id": [1], "name": ["Spice House"], "google_place_id": ["ChIJ-other"]}),
    )
    match = menu_inspect_service.foodpulse_place_match("ChIJ-missing")
    assert match["matched"] is False


def test_http_endpoint_does_not_call_google(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    from app.main import app

    client = TestClient(app)
    response = client.post("/analytics/nearby/menu-inspect", json={"google_place_id": "ChIJ1"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "google_has_no_menu"
    assert body["used_google_places"] is False
    assert body["items"] == []
