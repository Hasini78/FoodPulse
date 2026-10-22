"""Inspect a published restaurant page for structured menu data.

This module never calls Google Places, never writes Parquet, and never creates
database rows. Dish names and prices are copied only from schema.org JSON-LD
MenuItem records. Unstructured HTML is not turned into a menu.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from html import unescape
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx

from app.services import analytics_service as analytics
from app.services.analytics_service import AnalyticsDataError

FetchFn = Callable[[str], tuple[int, str, str]]

GOOGLE_FIELDS_NOTICE = (
    "Nearby Search on the Maps Demo Key requests id, displayName, location, "
    "formattedAddress, googleMapsURI, priceLevel, and optionally rating, "
    "userRatingCount, and primaryType. websiteUri and menu are not requested."
)
NO_MENU_NOTICE = (
    "Google Places did not return a menu for this listing. Paste a published "
    "restaurant website or menu URL to look for schema.org MenuItem records. "
    "FoodPulse sample dishes are not this restaurant's menu."
)
UNMATCHED_REASON = (
    "restaurants.parquet has no Google place id column, so this Google listing "
    "cannot be matched to a FoodPulse restaurant. Name and cuisine are not used as a match."
)
MATCH_FIELDS = ("google_place_id", "place_id", "google_places_id")
MAPS_HOSTS = {
    "google.com",
    "www.google.com",
    "maps.google.com",
    "maps.app.goo.gl",
    "www.google.co.in",
    "www.google.co.uk",
}
MENU_LINK_RE = re.compile(r"\b(menu|cardapio|carta)\b", re.I)
JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
ANCHOR_RE = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
MAX_BODY_CHARS = 1_000_000
FETCH_TIMEOUT_SECONDS = 8.0
MAX_FOLLOW_PAGES = 1

STATUS_GOOGLE_HAS_NO_MENU = "google_has_no_menu"
STATUS_INVALID_URL = "invalid_url"
STATUS_BLOCKED_URL = "blocked_url"
STATUS_MAPS_LISTING = "maps_listing_not_menu"
STATUS_FETCH_FAILED = "fetch_failed"
STATUS_NO_STRUCTURED_MENU = "no_structured_menu"
STATUS_MENU_FOUND = "menu_found"


def inspect_menu(
    url: str | None = None,
    google_place_id: str | None = None,
    fetch: FetchFn | None = None,
) -> dict[str, object]:
    """Inspect a published URL for JSON-LD menu items. Does not call Google."""
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    match = foodpulse_place_match(google_place_id)
    payload = {
        "status": STATUS_GOOGLE_HAS_NO_MENU,
        "retrieved_at": retrieved_at,
        "requested_url": None,
        "final_url": None,
        "source_links": [],
        "items": [],
        "suggestions": [],
        "foodpulse_match": match,
        "notice": NO_MENU_NOTICE,
        "google_fields": GOOGLE_FIELDS_NOTICE,
        "used_google_places": False,
        "used_foodpulse_history": False,
    }
    trimmed = (url or "").strip()
    if not trimmed:
        if match.get("matched"):
            foodpulse_items = foodpulse_catalog_for_match(match)
            payload["foodpulse_items"] = foodpulse_items
            payload["notice"] = (
                f"{NO_MENU_NOTICE} A FoodPulse restaurant row matched this Google place id exactly. "
                "Those catalog dishes are sample records for the matched id, not a live Google menu."
            )
        else:
            payload["foodpulse_items"] = []
        return payload

    payload["requested_url"] = trimmed
    kind, normalized, message = classify_url(trimmed)
    if kind == "invalid":
        payload["status"] = STATUS_INVALID_URL
        payload["notice"] = message
        payload["foodpulse_items"] = []
        return payload
    if kind == "blocked":
        payload["status"] = STATUS_BLOCKED_URL
        payload["notice"] = message
        payload["foodpulse_items"] = []
        return payload
    if kind == "maps":
        payload["status"] = STATUS_MAPS_LISTING
        payload["notice"] = (
            "That URL is a Google Maps listing, not a restaurant-published menu. "
            "This page does not scrape Google Maps HTML for dishes."
        )
        payload["source_links"] = [{"rel": "google_maps", "url": normalized, "label": "Google Maps listing"}]
        payload["foodpulse_items"] = foodpulse_catalog_for_match(match) if match.get("matched") else []
        return payload

    fetcher = fetch or fetch_public_url
    try:
        status_code, final_url, html = fetcher(normalized)
    except MenuInspectError as exc:
        payload["status"] = exc.status
        payload["notice"] = exc.message
        payload["foodpulse_items"] = []
        return payload
    payload["final_url"] = final_url
    payload["source_links"].append({"rel": "inspected", "url": final_url, "label": "Inspected page"})
    if status_code >= 400:
        payload["status"] = STATUS_FETCH_FAILED
        payload["notice"] = f"The published page returned HTTP {status_code}. No menu items were invented."
        payload["foodpulse_items"] = []
        return payload

    items, menu_links = extract_menu(html, final_url)
    if not items:
        for link in menu_links[:MAX_FOLLOW_PAGES]:
            href = str(link.get("url") or "")
            if not href or not same_host(final_url, href):
                continue
            kind, target, _message = classify_url(href)
            if kind != "ok":
                continue
            try:
                follow_status, follow_url, follow_html = fetcher(target)
            except MenuInspectError:
                continue
            payload["source_links"].append({"rel": "menu_candidate", "url": follow_url, "label": link.get("label") or "Menu page"})
            if follow_status >= 400:
                continue
            more, _ignored = extract_menu(follow_html, follow_url)
            items.extend(more)
            if items:
                payload["final_url"] = follow_url
                break
        else:
            payload["source_links"].extend(menu_links)

    payload["items"] = _unique_items(items)
    if payload["items"]:
        payload["status"] = STATUS_MENU_FOUND
        payload["suggestions"] = suggest_from_menu(payload["items"])
        payload["notice"] = (
            "These dishes were copied from schema.org JSON-LD MenuItem records on the published page. "
            "They are not FoodPulse sample dishes and not personalized ranks."
        )
    else:
        payload["status"] = STATUS_NO_STRUCTURED_MENU
        payload["notice"] = (
            "The published page was fetched, but no schema.org MenuItem records were found. "
            "Unstructured text is not turned into a menu, so no dishes were invented."
        )
        if menu_links:
            payload["source_links"].extend(menu_links)
            payload["notice"] += " A possible menu link is listed so you can open it yourself."
    payload["foodpulse_items"] = foodpulse_catalog_for_match(match) if match.get("matched") else []
    if match.get("matched"):
        payload["notice"] += (
            " A FoodPulse restaurant matched this Google place id exactly; those sample catalog "
            "dishes are listed separately and are not the live menu."
        )
    return payload


class MenuInspectError(Exception):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def classify_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid", url, "Enter an http or https URL for a published restaurant website or menu."
    host = parsed.hostname.lower() if parsed.hostname else ""
    if not host:
        return "invalid", url, "That URL has no hostname."
    if _is_maps_host(host):
        return "maps", url, "Google Maps listings are not restaurant-published menus."
    if _is_blocked_host(host):
        return "blocked", url, "That address is not a public website and was not fetched."
    return "ok", url, ""


def fetch_public_url(url: str) -> tuple[int, str, str]:
    """Fetch a public http(s) URL. Rejects private hosts. Does not send API keys."""
    kind, normalized, message = classify_url(url)
    if kind == "invalid":
        raise MenuInspectError(STATUS_INVALID_URL, message)
    if kind == "blocked":
        raise MenuInspectError(STATUS_BLOCKED_URL, message)
    if kind == "maps":
        raise MenuInspectError(STATUS_MAPS_LISTING, message)
    _assert_public_host(normalized)
    current = normalized
    try:
        with httpx.Client(follow_redirects=False, timeout=FETCH_TIMEOUT_SECONDS, headers=_headers()) as client:
            for _ in range(4):
                _assert_public_host(current)
                response = client.get(current)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    nxt = urljoin(current, location)
                    kind, nxt, message = classify_url(nxt)
                    if kind != "ok":
                        raise MenuInspectError(STATUS_BLOCKED_URL if kind == "blocked" else STATUS_INVALID_URL, message)
                    current = nxt
                    continue
                text = response.text[:MAX_BODY_CHARS]
                return response.status_code, str(response.url), text
    except MenuInspectError:
        raise
    except Exception as exc:
        raise MenuInspectError(
            STATUS_FETCH_FAILED,
            "The published page could not be retrieved. No menu items were invented.",
        ) from exc
    raise MenuInspectError(STATUS_FETCH_FAILED, "Too many redirects. No menu items were invented.")


def extract_menu(html: str, base_url: str) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    items: list[dict[str, object]] = []
    for node in _jsonld_nodes(html):
        items.extend(_menu_items_from_node(node, parent_section=None, source_url=base_url))
    return _unique_items(items), _menu_links(html, base_url)


def suggest_from_menu(items: list[dict[str, object]], limit: int = 8) -> list[dict[str, object]]:
    """Non-personalized picks from verified menu items only."""
    suggestions: list[dict[str, object]] = []
    seen: set[str] = set()
    by_section: dict[str, list[dict[str, object]]] = {}
    for item in items:
        section = str(item.get("category") or "Menu")
        by_section.setdefault(section, []).append(item)
    for section, rows in by_section.items():
        pick = rows[0]
        key = str(pick.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        suggestions.append(_suggestion(pick, f"Listed under {section} on this restaurant's published menu."))
        if len(suggestions) >= limit:
            return suggestions
    for item in items:
        key = str(item.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        suggestions.append(_suggestion(item, "Listed on this restaurant's published menu."))
        if len(suggestions) >= limit:
            break
    return suggestions


def foodpulse_place_match(google_place_id: str | None) -> dict[str, object]:
    """Match only on an exact stored Google place id. Never match by name or cuisine."""
    needle = (google_place_id or "").strip()
    unmatched = {
        "matched": False,
        "restaurant_id": None,
        "restaurant_name": None,
        "match_field": None,
        "reason": UNMATCHED_REASON,
    }
    if not needle:
        unmatched["reason"] = "No Google place id was supplied, so no FoodPulse restaurant can be matched."
        return unmatched
    try:
        path = analytics.processed_dir() / "restaurants.parquet"
        if not path.is_file():
            unmatched["reason"] = "restaurants.parquet is unavailable, so no FoodPulse restaurant can be matched."
            return unmatched
        import pyarrow.parquet as pq

        names = list(pq.read_schema(path).names)
        key = next((column for column in MATCH_FIELDS if column in names), None)
        if not key:
            return unmatched
        columns = [column for column in ("id", "name", key) if column in names]
        frame = analytics._read("restaurants.parquet", columns)
    except AnalyticsDataError:
        unmatched["reason"] = "restaurants.parquet is unavailable, so no FoodPulse restaurant can be matched."
        return unmatched
    for record in frame.to_dict("records"):
        stored = record.get(key)
        if analytics._missing(stored):
            continue
        token = str(stored).strip()
        if token == needle:
            restaurant_id = None if analytics._missing(record.get("id")) else str(record.get("id"))
            name = None if analytics._missing(record.get("name")) else str(record.get("name"))
            return {
                "matched": True,
                "restaurant_id": restaurant_id,
                "restaurant_name": name,
                "match_field": key,
                "reason": f"Exact {key} match on a FoodPulse restaurant row. Name and cuisine were not used.",
            }
    unmatched["reason"] = (
        f"No FoodPulse restaurant row stores Google place id {needle}. Name and cuisine were not used as a match."
    )
    return unmatched


def foodpulse_catalog_for_match(match: dict[str, object]) -> list[dict[str, object]]:
    if not match.get("matched") or not match.get("restaurant_id"):
        return []
    restaurant_id = str(match["restaurant_id"])
    try:
        foods = analytics._read("food_items.parquet", ["id", "restaurant_id", "name", "category", "price"])
    except AnalyticsDataError:
        return []
    items: list[dict[str, object]] = []
    for record in foods.to_dict("records"):
        row_restaurant = None if analytics._missing(record.get("restaurant_id")) else str(record.get("restaurant_id")).strip()
        if row_restaurant != restaurant_id:
            continue
        name = None if analytics._missing(record.get("name")) else str(record.get("name"))
        if not name:
            continue
        items.append(
            {
                "id": None if analytics._missing(record.get("id")) else str(record.get("id")),
                "name": name,
                "category": None if analytics._missing(record.get("category")) else str(record.get("category")),
                "price": analytics._json_value(record.get("price")),
                "description": None,
                "source": "foodpulse_catalog",
                "restaurant_id": restaurant_id,
                "reason": (
                    f"FoodPulse catalog dish for matched restaurant {restaurant_id}. "
                    "This is a sample record, not a live Google menu item."
                ),
            }
        )
    return items


def _suggestion(item: dict[str, object], reason: str) -> dict[str, object]:
    return {
        "name": item.get("name"),
        "category": item.get("category"),
        "price": item.get("price"),
        "currency": item.get("currency"),
        "description": item.get("description"),
        "source": item.get("source"),
        "source_url": item.get("source_url"),
        "personalized": False,
        "foodpulse_history": False,
        "reason": f"{reason} Not a personalized rank and not a FoodPulse sample dish.",
    }


def _jsonld_nodes(html: str) -> list[object]:
    nodes: list[object] = []
    for raw in JSONLD_RE.findall(html or ""):
        text = unescape(raw.strip())
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        nodes.extend(_flatten(data))
    return nodes


def _flatten(value: object) -> list[object]:
    if isinstance(value, list):
        items: list[object] = []
        for entry in value:
            items.extend(_flatten(entry))
        return items
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            return _flatten(graph) + [value]
        return [value]
    return []


def _menu_items_from_node(node: object, parent_section: str | None, source_url: str) -> list[dict[str, object]]:
    if not isinstance(node, dict):
        return []
    types = _types(node)
    items: list[dict[str, object]] = []
    section = parent_section
    if "MenuSection" in types:
        section = _text(node.get("name")) or parent_section
    if "MenuItem" in types:
        name = _text(node.get("name"))
        if name:
            price, currency = _offer_price(node.get("offers"))
            items.append(
                {
                    "name": name,
                    "description": _text(node.get("description")),
                    "price": price,
                    "currency": currency,
                    "category": section,
                    "source": "jsonld_menuitem",
                    "source_url": source_url,
                }
            )
    for key in ("hasMenuItem", "hasMenuSection", "hasMenu", "itemListElement", "menuAddOn"):
        child = node.get(key)
        if isinstance(child, list):
            for entry in child:
                items.extend(_menu_items_from_node(entry, section, source_url))
        elif isinstance(child, dict):
            items.extend(_menu_items_from_node(child, section, source_url))
    return items


def _types(node: dict[str, object]) -> set[str]:
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    names: set[str] = set()
    for value in values:
        if isinstance(value, str) and value.strip():
            names.add(value.strip().split("/")[-1])
    return names


def _offer_price(offers: object) -> tuple[object, str | None]:
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if not isinstance(offers, dict):
        return None, None
    price = offers.get("price")
    currency = _text(offers.get("priceCurrency"))
    if isinstance(price, (int, float)):
        return price, currency
    if isinstance(price, str) and price.strip():
        text = price.strip().replace(",", "")
        try:
            return float(text), currency
        except ValueError:
            return price.strip(), currency
    return None, currency


def _menu_links(html: str, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, label_html in ANCHOR_RE.findall(html or ""):
        label = TAG_RE.sub(" ", unescape(label_html)).strip()
        absolute = urljoin(base_url, href.strip())
        if absolute in seen:
            continue
        if not MENU_LINK_RE.search(href) and not MENU_LINK_RE.search(label):
            continue
        if not same_host(base_url, absolute):
            continue
        kind, _normalized, _message = classify_url(absolute)
        if kind != "ok":
            continue
        seen.add(absolute)
        links.append({"rel": "menu_candidate", "url": absolute, "label": label or "Menu"})
    return links


def _unique_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        name = str(item.get("name") or "").strip().lower()
        if not name:
            continue
        key = (name, str(item.get("category") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return _text(value.get("value") or value.get("@value") or value.get("name"))
    return None


def same_host(left: str, right: str) -> bool:
    host_a = (urlparse(left).hostname or "").lower()
    host_b = (urlparse(right).hostname or "").lower()
    return bool(host_a and host_a == host_b)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "FoodPulse-MenuInspect/0.1 (structured menu lookup; does not send API keys)",
        "Accept": "text/html,application/xhtml+xml,application/json",
    }


def _is_maps_host(host: str) -> bool:
    if host in MAPS_HOSTS:
        return True
    return host.endswith(".google.com") or host.endswith(".goo.gl")


def _is_blocked_host(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    if host.endswith(".local") or host.endswith(".internal") or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def _assert_public_host(url: str) -> None:
    host = urlparse(url).hostname
    if not host:
        raise MenuInspectError(STATUS_INVALID_URL, "That URL has no hostname.")
    if _is_blocked_host(host.lower()):
        raise MenuInspectError(STATUS_BLOCKED_URL, "That address is not a public website and was not fetched.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise MenuInspectError(STATUS_FETCH_FAILED, "The hostname could not be resolved. No menu items were invented.") from exc
    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not ip.is_global:
            raise MenuInspectError(STATUS_BLOCKED_URL, "That address is not a public website and was not fetched.")
