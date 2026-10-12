"""Mocked transformer-backend tests. They do not download a model."""

from __future__ import annotations

import pandas as pd
import pytest

from mining.sentiment.analyze import OUTPUT_COLUMNS, analyze_reviews
from mining.sentiment.transformer_backend import (
    clear_classifier_cache,
    map_id2label,
    score_texts,
    selected_backend,
)
from mining.sentiment.vader_baseline import score_text


class _FakeClassifier:
    def __init__(self, rows: dict[str, tuple[str, float]] | None = None) -> None:
        self.seen: list[list[str]] = []
        self.rows = rows or {}

    def predict(self, texts: list[str]) -> list[tuple[str, float]]:
        self.seen.append(list(texts))
        return [self.rows.get(text, ("neutral", 0.55)) for text in texts]


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_classifier_cache()
    yield
    clear_classifier_cache()


def test_backend_selection_rejects_unknown_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTIMENT_MODEL", raising=False)
    assert selected_backend() == "vader"
    monkeypatch.setenv("SENTIMENT_MODEL", "transformer")
    assert selected_backend() == "transformer"
    monkeypatch.setenv("SENTIMENT_MODEL", "roberta")
    with pytest.raises(RuntimeError, match="vader"):
        selected_backend()


def test_label_mapping_uses_config_names_and_rejects_unknown_ids() -> None:
    mapped = map_id2label({0: "negative", 1: "Neutral", 2: "POSITIVE"})
    assert mapped == {0: "negative", 1: "neutral", 2: "positive"}
    with pytest.raises(RuntimeError, match="not one of"):
        map_id2label({0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"})
    with pytest.raises(RuntimeError, match="must contain"):
        map_id2label({0: "positive", 1: "negative"})


def test_empty_text_is_invalid_and_batches_skip_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIMENT_MODEL", "transformer")
    monkeypatch.setenv("SENTIMENT_BATCH_SIZE", "2")
    fake = _FakeClassifier(
        {
            "the food was amazing": ("positive", 0.93),
            "the food was terrible": ("negative", 0.81),
            "the order arrived today": ("neutral", 0.66),
        }
    )
    monkeypatch.setattr("mining.sentiment.transformer_backend.get_classifier", lambda: fake)
    scored = score_texts(["The food was amazing", None, "  ", "The food was terrible", "<br>", "The order arrived today"])
    assert [item.label for item in scored] == ["positive", "invalid", "invalid", "negative", "invalid", "neutral"]
    assert scored[0].confidence == pytest.approx(0.93)
    assert scored[0].backend == "transformer"
    assert scored[1].confidence is None
    assert fake.seen == [["the food was amazing", "the food was terrible"], ["the order arrived today"]]


def test_confidence_must_stay_inside_zero_and_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIMENT_MODEL", "transformer")

    class _Bad:
        def predict(self, texts: list[str]) -> list[tuple[str, float]]:
            return [("positive", 1.2) for _ in texts]

    monkeypatch.setattr("mining.sentiment.transformer_backend.get_classifier", lambda: _Bad())
    with pytest.raises(RuntimeError, match="outside the range"):
        score_texts(["The food was good"])


def test_invalid_config_batch_size_and_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIMENT_MODEL", "transformer")
    monkeypatch.setenv("SENTIMENT_BATCH_SIZE", "zero")
    with pytest.raises(RuntimeError, match="SENTIMENT_BATCH_SIZE"):
        score_texts(["hello"])
    monkeypatch.setenv("SENTIMENT_BATCH_SIZE", "4")
    monkeypatch.setenv("SENTIMENT_DEVICE", "gpu")
    with pytest.raises(RuntimeError, match="SENTIMENT_DEVICE"):
        score_texts(["hello"])


def test_missing_dependency_and_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIMENT_MODEL", "transformer")
    monkeypatch.setenv("SENTIMENT_TRANSFORMER_MODEL", "cardiffnlp/twitter-roberta-base-sentiment-latest")

    def _missing():
        raise ImportError("transformers")

    monkeypatch.setattr("mining.sentiment.transformer_backend._import_runtime", _missing)
    with pytest.raises(RuntimeError, match="not installed"):
        score_texts(["The food was good"])

    def _broken():
        class _Config:
            @staticmethod
            def from_pretrained(_name: str):
                raise OSError("download failed")

        return object(), _Config, _Config, _Config

    monkeypatch.setattr("mining.sentiment.transformer_backend._import_runtime", _broken)
    with pytest.raises(RuntimeError, match="Could not load transformer model"):
        score_texts(["The food was good"])


def test_analyze_keeps_schema_and_vader_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTIMENT_MODEL", raising=False)
    reviews = pd.DataFrame({"id": [1, 2], "review_text": ["The food was amazing", None]})
    scored = analyze_reviews(reviews)
    assert list(scored.columns) == list(OUTPUT_COLUMNS)
    assert scored.loc[0, "overall_sentiment"] == "positive"
    assert scored.loc[1, "overall_sentiment"] == "invalid"
    assert scored.loc[1, "overall_score"] is None or pd.isna(scored.loc[1, "overall_score"])
    assert score_text("The food was amazing").backend == "vader"

    monkeypatch.setenv("SENTIMENT_MODEL", "nope")
    with pytest.raises(RuntimeError, match="SENTIMENT_MODEL"):
        analyze_reviews(reviews)


def test_analyze_writes_transformer_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIMENT_MODEL", "transformer")
    fake = _FakeClassifier({"the food was amazing": ("positive", 0.42)})
    monkeypatch.setattr("mining.sentiment.transformer_backend.get_classifier", lambda: fake)
    scored = analyze_reviews(pd.DataFrame({"id": [7], "review_text": ["The food was amazing"]}))
    assert list(scored.columns) == list(OUTPUT_COLUMNS)
    assert scored.loc[0, "overall_sentiment"] == "positive"
    assert scored.loc[0, "overall_score"] == pytest.approx(0.42)
    assert scored.loc[0, "food_sent"] == "positive"
