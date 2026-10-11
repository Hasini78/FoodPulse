"""Tests for VADER sentiment, aspects, evaluation, and optional persistence."""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from mining.sentiment.aggregate import aggregate_trends
from mining.sentiment.analyze import analyze_reviews
from mining.sentiment.aspects import NOT_MENTIONED, aspect_sentiments
from mining.sentiment.evaluate import evaluate, rating_proxy
from mining.sentiment.export import export_sentiment, warehouse_frame
from mining.sentiment.persist import upsert_review_sentiment
from mining.sentiment.preprocess import prepare_text
from mining.sentiment.transformer_backend import score_texts
from mining.sentiment.vader_baseline import score_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_REVIEWS = PROJECT_ROOT / "data" / "sample" / "reviews.csv"
STAMP = datetime(2026, 10, 11, tzinfo=timezone.utc)
BIRYANI = "The biryani was amazing, but the service was extremely slow."


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_vader_positive_negative_neutral_and_empty() -> None:
    positive = score_text("The food was amazing and delicious")
    negative = score_text("The food was not good")
    neutral = score_text("The order arrived today")
    invalid = score_text("  <p> </p> ")
    assert positive.label == "positive" and positive.compound is not None and positive.compound >= 0.05
    assert negative.label == "negative" and negative.compound is not None and negative.compound <= -0.05
    assert neutral.label == "neutral"
    assert invalid.label == "invalid"
    assert invalid.compound is None


def test_preprocessing_keeps_negation_and_punctuation() -> None:
    prepared = prepare_text("  <b>Not</b> good! ")
    assert "not" in prepared.lemmas
    assert "!" in prepared.tokens
    assert prepared.text == "not good!"


def test_biryani_contrast_aspects() -> None:
    aspects = aspect_sentiments(BIRYANI)
    assert aspects["food"] == "positive"
    assert aspects["service"] == "negative"
    assert aspects["ambience"] == NOT_MENTIONED
    assert aspects["price"] == NOT_MENTIONED
    overall = score_text(BIRYANI)
    assert overall.label == "positive"


def test_negation_one_aspect_and_multiple_aspects() -> None:
    negated = aspect_sentiments("The food was not good.")
    assert negated["food"] == "negative"
    assert negated["service"] == NOT_MENTIONED

    flipped = aspect_sentiments("The service was not slow.")
    assert flipped["service"] == "positive"

    price_only = aspect_sentiments("The prices were reasonable.")
    assert price_only["price"] == "positive"
    assert price_only["food"] == NOT_MENTIONED
    assert price_only["ambience"] == NOT_MENTIONED

    both = aspect_sentiments("The ambience was nice but the food was not good.")
    assert both["ambience"] == "positive"
    assert both["food"] == "negative"
    assert both["service"] == NOT_MENTIONED
    assert both["price"] == NOT_MENTIONED


def test_missing_text_is_not_neutral() -> None:
    for value in (None, "", "   ", "<br>"):
        aspects = aspect_sentiments(value)
        assert set(aspects.values()) == {NOT_MENTIONED}
        assert score_text(value).label == "invalid"


def test_rating_proxy_skips_missing_values() -> None:
    assert rating_proxy(1) == "negative"
    assert rating_proxy(3) == "neutral"
    assert rating_proxy(5) == "positive"
    assert rating_proxy(None) is None
    assert rating_proxy(float("nan")) is None


def test_evaluation_metrics_and_confusion_matrix(tmp_path: Path) -> None:
    reviews = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "rating": [5, 1, None, 3],
            "review_text": [
                "The food was amazing",
                "The food was not good",
                "The food was amazing",
                "The order arrived today",
            ],
        }
    )
    scored = analyze_reviews(reviews, analyzed_at=STAMP)
    payload = evaluate(scored, reviews, tmp_path)
    assert payload["rows_scored"] == 4
    assert payload["rows_skipped_missing_or_invalid_rating"] == 1
    assert payload["per_class"]["neutral"]["support"] == 1
    assert (tmp_path / "confusion_matrix.png").is_file()
    assert (tmp_path / "evaluation.json").is_file()
    assert "weak supervision" in str(payload["note"])


def test_aggregations_do_not_duplicate_reviews() -> None:
    reviews = pd.DataFrame(
        {
            "id": [1],
            "restaurant_id": [10],
            "created_at": ["2026-01-09 14:45:53+00:00"],
            "rating": [4],
            "review_text": ["Loved the flavors and the prices were fair."],
        }
    )
    restaurants = pd.DataFrame(
        {"id": [10, 10], "cuisine_type": ["Indian", "Indian"], "location_id": [3, 3]}
    )
    locations = pd.DataFrame({"id": [3, 3], "city": ["Pune", "Pune"]})
    scored = analyze_reviews(reviews, analyzed_at=STAMP)
    trends = aggregate_trends(scored, reviews, restaurants, locations)
    assert trends["by_restaurant"].loc[0, "review_count"] == 1
    assert trends["by_city"].loc[0, "city"] == "Pune"
    assert trends["by_city"].loc[0, "review_count"] == 1
    assert trends["by_cuisine"].loc[0, "cuisine_type"] == "Indian"
    assert trends["by_month"].loc[0, "month"] == "2026-01"
    assert trends["by_month"].loc[0, "review_count"] == 1


def test_export_columns(tmp_path: Path) -> None:
    reviews = pd.DataFrame({"id": [7], "review_text": [BIRYANI]})
    scored = analyze_reviews(reviews, analyzed_at=STAMP)
    exported = warehouse_frame(scored)
    assert list(exported.columns) == [
        "review_id",
        "overall_sentiment",
        "overall_score",
        "food_sent",
        "service_sent",
        "ambience_sent",
        "price_sent",
        "analyzed_at",
    ]
    path = export_sentiment(scored, tmp_path / "review_sentiment.parquet")
    loaded = pd.read_parquet(path)
    assert loaded.loc[0, "review_id"] == 7
    assert loaded.loc[0, "food_sent"] == "positive"
    assert loaded.loc[0, "service_sent"] == "negative"


def test_upsert_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    reviews = pd.DataFrame({"id": [4], "review_text": ["The food was amazing"]})
    first = analyze_reviews(reviews, analyzed_at=STAMP)
    second = first.copy()
    second.loc[0, "overall_score"] = 0.99
    second.loc[0, "overall_sentiment"] = "positive"
    assert upsert_review_sentiment(first, engine) == 1
    assert upsert_review_sentiment(second, engine) == 1
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT review_id, overall_score FROM review_sentiment")).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 4
    assert rows[0][1] == pytest.approx(0.99)


def test_transformer_is_not_loaded_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTIMENT_MODEL", raising=False)
    score_text("The food was good")
    assert "transformers" not in sys.modules
    with pytest.raises(RuntimeError, match="not selected"):
        score_texts(["The food was good"])


def test_sample_reviews_stay_unchanged_and_are_fully_scored() -> None:
    before = _sha256(SAMPLE_REVIEWS)
    reviews = pd.read_csv(SAMPLE_REVIEWS)
    scored = analyze_reviews(reviews, analyzed_at=STAMP)
    assert _sha256(SAMPLE_REVIEWS) == before
    assert len(scored) == len(reviews) == 3000
    assert scored["review_id"].nunique() == 3000
    assert set(scored["overall_sentiment"]).issubset({"positive", "negative", "neutral", "invalid"})
    example = aspect_sentiments(BIRYANI)
    assert example["food"] == "positive"
    assert example["service"] == "negative"
