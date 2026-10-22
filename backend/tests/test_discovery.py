"""Discovery rows over temporary Parquet. This does not write data/processed."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services import analytics_service, discovery_service


def _write(directory: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(directory / name, index=False)


def _world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    _write(
        tmp_path,
        "food_items.parquet",
        pd.DataFrame(
            {
                "id": [10, 11, 12, 20, 21, 22],
                "restaurant_id": [1, 1, 1, 2, 2, 2],
                "name": ["Pad Thai", "Spring Roll", "Green Curry", "Biryani", "Raita", "Kheer"],
                "category": ["Main", "Starter", "Main", "Main", "Side", "Dessert"],
                "price": [12.0, 6.0, 13.0, 14.0, 4.0, 5.0],
            }
        ),
    )
    _write(
        tmp_path,
        "restaurants.parquet",
        pd.DataFrame(
            {
                "id": [1, 2],
                "name": ["Thai House", "Spice Room"],
                "cuisine_type": ["Thai", "Indian"],
                "location_id": [5, 6],
            }
        ),
    )
    _write(tmp_path, "locations.parquet", pd.DataFrame({"id": [5, 6], "city": ["Pune", "Mumbai"]}))
    _write(
        tmp_path,
        "restaurant_features.parquet",
        pd.DataFrame(
            {
                "restaurant_id": [1, 2],
                "avg_rating": [4.5, 3.2],
                "review_volume": [8, 2],
                "order_volume": [10, 3],
            }
        ),
    )
    _write(
        tmp_path,
        "sentiment_by_restaurant.parquet",
        pd.DataFrame(
            {
                "restaurant_id": [1, 2],
                "review_count": [8, 2],
                "positive_count": [7, 1],
                "mean_score": [0.6, 0.1],
            }
        ),
    )
    _write(
        tmp_path,
        "orders.parquet",
        pd.DataFrame(
            {
                "id": [100, 101, 103, 102, 200],
                "customer_id": [1, 1, 1, 1, 9],
                "restaurant_id": [1, 1, 1, 1, 2],
                "status": ["completed", "Completed", "completed", "cancelled", "completed"],
            }
        ),
    )
    _write(
        tmp_path,
        "order_items.parquet",
        pd.DataFrame(
            {
                "order_id": [100, 100, 101, 103, 102, 200],
                "food_item_id": [10, 10, 10, 10, 11, 20],
            }
        ),
    )
    _write(
        tmp_path,
        "food_recommendations.parquet",
        pd.DataFrame(
            {
                "customer_id": ["1", "1", "1", "2"],
                "food_item_id": ["11", "11", "21", "20"],
                "restaurant_id": ["1", "1", "2", "2"],
                "recommendation_score": [0.9, 0.8, 0.1, 0.4],
                "rank": [1, 2, 3, 1],
                "reason": [
                    "associated with a previously purchased item",
                    "associated with a previously purchased item",
                    "frequently purchased cuisine",
                    "general pick for limited history",
                ],
            }
        ),
    )
    _write(
        tmp_path,
        "restaurant_recommendations.parquet",
        pd.DataFrame(
            {
                "customer_id": ["1", "2"],
                "restaurant_id": ["2", "1"],
                "recommendation_score": [0.7, 0.3],
                "rank": [1, 1],
                "reason": ["highly rated in preferred cuisine", "general pick for limited history"],
            }
        ),
    )
    _write(
        tmp_path,
        "association_rules.parquet",
        pd.DataFrame(
            {
                "antecedent_ids": ["10", "10", "20"],
                "antecedent_names": ["Pad Thai", "Pad Thai", "Biryani"],
                "consequent_ids": ["11", "21", "21"],
                "consequent_names": ["Spring Roll", "Raita", "Raita"],
                "support": [0.05, 0.01, 0.05],
                "confidence": [0.6, 0.9, 0.6],
                "lift": [3.0, 1.2, 2.0],
                "support_count": [20, 10, 20],
            }
        ),
    )
    _write(tmp_path, "customers.parquet", pd.DataFrame({"id": [1, 2, 9]}))
    return tmp_path


def _section(payload: dict, section_id: str) -> dict:
    return next(item for item in payload["sections"] if item["id"] == section_id)


def test_picked_for_you_deduplicates_and_uses_plain_reasons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1", limit=8)
    picked = _section(payload, "picked_for_you")["items"]
    assert [item["id"] for item in picked] == ["11", "21"]
    assert picked[0]["reason"] == "Often bought with something you already ordered"
    assert picked[0]["fallback"] is False
    assert picked[0]["image_url"] is None
    assert payload["persistence"]["like"] is False
    assert payload["history"]["cuisines"] == ["Thai"]
    assert payload["history"]["distinct_foods"] == 1
    other = discovery_service.discovery("2")
    assert [item["id"] for item in _section(other, "picked_for_you")["items"]] == ["20"]
    assert "20" not in [item["id"] for item in picked]
    assert "11" not in [item["id"] for item in _section(other, "picked_for_you")["items"]]


def test_thin_history_is_labelled_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("2")
    assert payload["history"]["thin_history"] is True
    assert payload["history"]["completed_orders"] == 0
    picked = _section(payload, "picked_for_you")["items"]
    assert picked[0]["fallback"] is True
    assert "thin" in picked[0]["reason"].lower() or "limited history" in picked[0]["reason"].lower()
    similar = _section(payload, "similar_to_what_you_like")
    assert similar["items"] == []
    together = _section(payload, "frequently_bought_together")
    assert together["items"] == []


def test_popular_uses_completed_orders_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1")
    popular = _section(payload, "popular_choices")["items"]
    foods = [item for item in popular if item["kind"] == "food"]
    restaurants = [item for item in popular if item["kind"] == "restaurant"]
    assert foods[0]["id"] == "10"
    assert foods[0]["evidence"] == 4
    assert foods[0]["reason"] == "Popular across all customers in the completed-order data"
    assert restaurants[0]["id"] == "1"
    assert restaurants[0]["metric"] == "completed_orders"
    assert _section(payload, "popular_choices")["metric"] == "completed_orders"


def test_association_respects_evidence_and_is_not_causation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1", min_support_count=14, min_confidence=0.3, min_lift=1.0)
    together = _section(payload, "frequently_bought_together")["items"]
    assert [item["id"] for item in together] == ["11"]
    assert "Often bought with Pad Thai" in together[0]["reason"]
    assert "not causation" in together[0]["reason"]
    assert together[0]["lift"] == pytest.approx(3.0)
    assert together[0]["confidence"] == pytest.approx(0.6)
    assert together[0]["support_count"] == 20
    assert together[0]["support"] == pytest.approx(0.05)
    weak = discovery_service.discovery("1", min_support_count=100)
    assert _section(weak, "frequently_bought_together")["items"] == []


def test_similar_and_explore_avoid_repeats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1")
    similar = _section(payload, "similar_to_what_you_like")["items"]
    assert [item["id"] for item in similar] == ["12"]
    assert similar[0]["reason"] == "Based on your Thai orders"
    assert "10" not in [item["id"] for item in similar]
    explore = _section(payload, "explore_something_new")["items"]
    popular_foods = [item["id"] for item in _section(payload, "popular_choices")["items"] if item["kind"] == "food"]
    shown = {
        item["id"]
        for item in _section(payload, "picked_for_you")["items"] + similar + _section(payload, "frequently_bought_together")["items"]
    }
    shown.update(popular_foods)
    assert shown.isdisjoint({item["id"] for item in explore})
    assert [item["id"] for item in explore] == ["22"]
    assert all(item["cuisine"] == "Indian" for item in explore)
    assert "20" not in [item["id"] for item in explore]
    restaurants = _section(payload, "restaurants_for_you")["items"]
    assert restaurants[0]["city"] == "Mumbai"
    assert restaurants[0]["cuisine"] == "Indian"


def test_invalid_customer_and_missing_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    with pytest.raises(analytics_service.AnalyticsDataError, match="invalid"):
        discovery_service.discovery("1/../secret")
    payload = discovery_service.discovery("1")
    assert payload["sections"]
    assert payload["unavailable"]
    from app.main import app

    client = TestClient(app)
    missing = client.get("/analytics/recommendations/1/discovery")
    assert missing.status_code == 200
    stored = client.get("/analytics/recommendations/8")
    assert stored.status_code == 404


def test_existing_recommendation_contract_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = analytics_service.recommendations_for("1")
    assert payload["foods"][0]["food_name"] == "Spring Roll"
    assert payload["foods"][0]["reason"] == "associated with a previously purchased item"
    from app.main import app

    client = TestClient(app)
    stored = client.get("/analytics/recommendations/1")
    assert stored.status_code == 200
    stored_body = stored.json()
    assert stored_body["foods"][0]["reason"] == "associated with a previously purchased item"
    assert "sections" not in stored_body
    response = client.get("/analytics/recommendations/1/discovery", params={"limit": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "processed_parquet"
    assert [section["id"] for section in body["sections"]] == [
        "picked_for_you",
        "popular_choices",
        "similar_to_what_you_like",
        "frequently_bought_together",
        "restaurants_for_you",
        "explore_something_new",
    ]
    assert body["notice"].startswith("These rows read stored")


def test_default_filters_keep_unfiltered_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1", cuisine="All", category="")
    assert payload["filters"]["applied"] == {"cuisine": None, "category": None}
    assert payload["filters"]["cuisine_categories"]["Thai"] == ["Main", "Starter"]
    assert [item["id"] for item in _section(payload, "picked_for_you")["items"]] == ["11", "21"]
    assert _section(payload, "popular_choices")["items"]


def test_valid_cuisine_category_combination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1", cuisine="THAI", category="starter")
    picked = _section(payload, "picked_for_you")["items"]
    assert [item["id"] for item in picked] == ["11"]
    assert picked[0]["category"] == "Starter"
    popular_foods = [item for item in _section(payload, "popular_choices")["items"] if item["kind"] == "food"]
    assert all(item["cuisine"] == "Thai" and item["category"] == "Starter" for item in popular_foods)
    restaurants = [item for item in _section(payload, "popular_choices")["items"] if item["kind"] == "restaurant"]
    assert restaurants and all(item["cuisine"] == "Thai" for item in restaurants)


def test_empty_korean_dessert_keeps_korean_restaurants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    restaurants = pd.read_parquet(tmp_path / "restaurants.parquet")
    restaurants = pd.concat(
        [
            restaurants,
            pd.DataFrame({"id": [3], "name": ["Seoul Kitchen"], "cuisine_type": ["Korean"], "location_id": [5]}),
        ],
        ignore_index=True,
    )
    restaurants.to_parquet(tmp_path / "restaurants.parquet", index=False)
    foods = pd.read_parquet(tmp_path / "food_items.parquet")
    foods = pd.concat(
        [
            foods,
            pd.DataFrame(
                {
                    "id": [30],
                    "restaurant_id": [3],
                    "name": ["Kimchi Fried Rice"],
                    "category": ["Main"],
                    "price": [11.0],
                }
            ),
        ],
        ignore_index=True,
    )
    foods.to_parquet(tmp_path / "food_items.parquet", index=False)
    analytics_service._CACHE.clear()
    payload = discovery_service.discovery("1", cuisine="korean", category="DESSERT")
    foods_only = [item for section in payload["sections"] for item in section["items"] if item["kind"] == "food"]
    assert foods_only == []
    popular_restaurants = [item for item in _section(payload, "popular_choices")["items"] if item["kind"] == "restaurant"]
    assert [item["id"] for item in popular_restaurants] == ["3"]
    assert payload["filters"]["cuisine_categories"]["Korean"] == ["Main"]


def test_customer_specific_recommendations_stay_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    first = discovery_service.discovery("1")
    second = discovery_service.discovery("2")
    assert [item["id"] for item in _section(first, "picked_for_you")["items"]] == ["11", "21"]
    assert [item["id"] for item in _section(second, "picked_for_you")["items"]] == ["20"]
    assert [item["id"] for item in _section(first, "restaurants_for_you")["items"]] == ["2"]
    assert [item["id"] for item in _section(second, "restaurants_for_you")["items"]] == ["1"]


def test_duplicate_dish_names_keep_other_restaurants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    foods = pd.read_parquet(tmp_path / "food_items.parquet")
    foods = pd.concat(
        [
            foods,
            pd.DataFrame(
                {
                    "id": [13, 99, 23],
                    "restaurant_id": [1, 1, 2],
                    "name": ["Spring Roll", "Spring Roll", "Spring Roll"],
                    "category": ["Starter", "Starter", "Starter"],
                    "price": [6.0, 6.5, 7.0],
                }
            ),
        ],
        ignore_index=True,
    )
    foods.to_parquet(tmp_path / "food_items.parquet", index=False)
    recs = pd.read_parquet(tmp_path / "food_recommendations.parquet")
    recs = pd.concat(
        [
            recs,
            pd.DataFrame(
                {
                    "customer_id": ["1", "1", "1"],
                    "food_item_id": ["13", "99", "23"],
                    "restaurant_id": ["1", "1", "2"],
                    "recommendation_score": [0.85, 0.84, 0.7],
                    "rank": [4, 5, 6],
                    "reason": ["frequently purchased cuisine"] * 3,
                }
            ),
        ],
        ignore_index=True,
    )
    recs.to_parquet(tmp_path / "food_recommendations.parquet", index=False)
    analytics_service._CACHE.clear()
    picked = _section(discovery_service.discovery("1"), "picked_for_you")["items"]
    names = [(item["name"], item["restaurant_id"]) for item in picked]
    assert names.count(("Spring Roll", "1")) == 1
    assert ("Spring Roll", "2") in names
    assert {item["id"] for item in picked if item["name"] == "Spring Roll" and item["restaurant_id"] == "1"} == {"11"}
    spring = next(item for item in picked if item["id"] == "23")
    assert spring["restaurant_name"] == "Spice Room"


def test_ratings_are_restaurant_sample_averages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1")
    picked = _section(payload, "picked_for_you")["items"][0]
    assert picked["rating"] == pytest.approx(4.5)
    assert picked["rating_label"] == "Restaurant sample avg"
    assert "not a dish rating" in picked["rating_source"]
    assert "sample reviews" in payload["rating_notice"]
    assert "not live public" in payload["notice"]


def test_section_scopes_mark_global_versus_personalized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1")
    scopes = {section["id"]: section["scope"] for section in payload["sections"]}
    assert scopes["picked_for_you"] == "personalized"
    assert scopes["restaurants_for_you"] == "personalized"
    assert scopes["popular_choices"] == "global"
    assert scopes["frequently_bought_together"] == "association"
    assert scopes["similar_to_what_you_like"] == "cuisine_history"
    assert scopes["explore_something_new"] == "new_cuisine"
    assert "Personalized" in _section(payload, "picked_for_you")["description"]
    assert "Global" in _section(payload, "popular_choices")["description"]
    assert "Association" in _section(payload, "frequently_bought_together")["description"]
    empty = discovery_service.discovery("2")
    similar = _section(empty, "similar_to_what_you_like")
    together = _section(empty, "frequently_bought_together")
    assert similar["items"] == []
    assert similar["empty_kind"] == "no_history"
    assert together["empty_kind"] == "no_history"


def test_missing_source_empty_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOODPULSE_PROCESSED_DIR", str(tmp_path))
    analytics_service._CACHE.clear()
    payload = discovery_service.discovery("1")
    picked = _section(payload, "picked_for_you")
    assert picked["items"] == []
    assert picked["empty_kind"] == "missing_data"
    assert "unavailable" in picked["empty_message"].lower()


def test_cuisine_filter_miss_keeps_unfiltered_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1", cuisine="Indian")
    picked = _section(payload, "picked_for_you")
    assert [item["id"] for item in picked["items"]] == ["21"]
    assert picked["scope"] == "personalized"
    assert picked["fallback_kind"] is None
    similar = _section(payload, "similar_to_what_you_like")
    assert similar["items"]
    assert similar["scope"] == "cuisine_catalog"
    assert similar["fallback_kind"] == "cuisine_catalog"
    assert all(item["cuisine"] == "Indian" for item in similar["items"])
    assert all(item["fallback"] is True for item in similar["items"])
    assert all(item.get("lift") is None for item in similar["items"])
    assert "not a stored personal" in similar["description"].lower() or "not this customer" in similar["description"].lower()
    assert similar["unfiltered_count"] > 0
    assert "Thai" in similar["available_cuisines"]
    together = _section(payload, "frequently_bought_together")
    assert together["items"] == []
    assert together["empty_kind"] == "filter_miss"
    assert together["scope"] == "association"
    popular_foods = [item for item in _section(payload, "popular_choices")["items"] if item["kind"] == "food"]
    assert popular_foods
    assert all(item["cuisine"] == "Indian" for item in popular_foods)
    missing = discovery_service.discovery("1", cuisine="French")
    popular = _section(missing, "popular_choices")
    assert popular["items"] == []
    assert popular["empty_kind"] == "filter_miss"
    assert popular["unfiltered_count"] > 0
    similar_missing = _section(missing, "similar_to_what_you_like")
    assert similar_missing["items"] == []
    assert similar_missing["empty_kind"] == "filter_miss"


def test_discovery_http_accepts_cuisine_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    response = client.get("/analytics/recommendations/1/discovery", params={"cuisine": "Indian", "category": "Side"})
    assert response.status_code == 200
    body = response.json()
    picked = next(section for section in body["sections"] if section["id"] == "picked_for_you")["items"]
    assert [item["id"] for item in picked] == ["21"]


def test_catalog_fallback_is_not_labelled_personalized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("1", cuisine="Indian")
    similar = _section(payload, "similar_to_what_you_like")
    assert similar["explanation"]["fallback"] is True
    assert similar["explanation"]["kind"] == "cuisine_catalog"
    assert "collaborative filtering" in similar["explanation"]["algorithm"].lower() or "not a stored personal" in similar["explanation"]["algorithm"].lower()
    assert similar["explanation"]["data_source"]
    restaurants = _section(payload, "restaurants_for_you")
    assert restaurants["scope"] == "personalized"
    assert [item["id"] for item in restaurants["items"]] == ["2"]
    together = _section(payload, "frequently_bought_together")
    assert together["items"] == []
    assert together["explanation"]["kind"] == "association"
    assert together["explanation"]["fallback"] is False


def test_missing_stored_ranks_use_popular_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("9")
    picked = _section(payload, "picked_for_you")
    assert picked["items"]
    assert picked["scope"] == "global"
    assert picked["fallback_kind"] == "cold_start"
    assert picked["explanation"]["fallback"] is True
    assert picked["explanation"]["kind"] == "global"
    assert all(item["fallback"] is True for item in picked["items"])
    assert all(item["metric"] == "completed_orders" for item in picked["items"])
    assert all("not a stored personal" in item["reason"].lower() or "no matching stored" in item["reason"].lower() for item in picked["items"])
    similar = _section(payload, "similar_to_what_you_like")
    assert similar["scope"] == "cuisine_history"
    assert similar["fallback_kind"] is None
    restaurants = _section(payload, "restaurants_for_you")
    assert restaurants["fallback_kind"] == "cold_start"
    assert restaurants["scope"] == "global"
    together = _section(payload, "frequently_bought_together")
    assert [item["id"] for item in together["items"]] == ["21"]
    assert together["scope"] == "association"
    assert together["items"][0]["lift"] == pytest.approx(2.0)
    assert together["explanation"]["fallback"] is False


def test_association_is_never_filled_from_popularity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _world(tmp_path, monkeypatch)
    payload = discovery_service.discovery("2", cuisine="Thai")
    together = _section(payload, "frequently_bought_together")
    assert together["items"] == []
    assert together["empty_kind"] == "no_history"
    assert together["scope"] == "association"
    picked = _section(payload, "picked_for_you")
    assert picked["items"]
    assert picked["scope"] == "cuisine_catalog"
    assert all(item["cuisine"] == "Thai" for item in picked["items"] if item["kind"] == "food")
    assert all("not a stored personal" in item["reason"].lower() for item in picked["items"])
    native = discovery_service.discovery("1")
    assert _section(native, "picked_for_you")["explanation"]["kind"] == "personalized"
    assert _section(native, "picked_for_you")["explanation"]["fallback"] is False
    assert "not a purchase probability" in _section(native, "picked_for_you")["explanation"]["algorithm"]
