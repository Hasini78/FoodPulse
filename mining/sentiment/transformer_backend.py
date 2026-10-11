"""Optional Hugging Face sentiment backend.

Nothing in this module downloads or loads a model unless
``SENTIMENT_MODEL=transformer``. The default VADER workflow never imports
``transformers``.
"""

from __future__ import annotations

import logging
import os

from mining.sentiment.preprocess import clean_text
from mining.sentiment.vader_baseline import SentimentScore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
_LABELS = {
    "positive": "positive",
    "negative": "negative",
    "neutral": "neutral",
    "label_2": "positive",
    "label_0": "negative",
    "label_1": "neutral",
}


def transformer_selected() -> bool:
    """Return True only when the transformer backend was explicitly requested."""
    return os.getenv("SENTIMENT_MODEL", "vader").strip().lower() == "transformer"


def score_texts(texts: list[object]) -> list[SentimentScore]:
    """Score a batch with the configured transformer on CPU unless overridden."""
    if not transformer_selected():
        raise RuntimeError(
            "Transformer sentiment is not selected. Set SENTIMENT_MODEL=transformer "
            "to load it. The default backend is VADER and does not download a model."
        )
    try:
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError(
            "SENTIMENT_MODEL=transformer but the transformers package is not installed. "
            "The default VADER path does not need it."
        ) from exc

    model_name = os.getenv("SENTIMENT_TRANSFORMER_MODEL", DEFAULT_MODEL).strip()
    if not model_name:
        raise RuntimeError("SENTIMENT_TRANSFORMER_MODEL is empty, so no model will be loaded.")
    batch_size = _batch_size()
    device = _device()
    logger.info("Loading transformer %s on device %s", model_name, device)
    try:
        classifier = pipeline("sentiment-analysis", model=model_name, tokenizer=model_name, device=device)
    except Exception as exc:
        if device != -1:
            logger.warning("Transformer device %s failed (%s); falling back to CPU", device, exc)
            classifier = pipeline("sentiment-analysis", model=model_name, tokenizer=model_name, device=-1)
        else:
            raise RuntimeError(f"Could not load transformer model '{model_name}'.") from exc

    prepared = [clean_text(text) or " " for text in texts]
    results: list[SentimentScore] = []
    for start in range(0, len(prepared), batch_size):
        chunk = prepared[start : start + batch_size]
        for source, prediction in zip(chunk, classifier(chunk, batch_size=batch_size, truncation=True), strict=True):
            if not source.strip():
                results.append(SentimentScore(label="invalid", compound=None))
                continue
            label = _LABELS.get(str(prediction["label"]).lower(), "neutral")
            score = float(prediction["score"])
            compound = score if label == "positive" else -score if label == "negative" else 0.0
            results.append(SentimentScore(label=label, compound=compound))
    return results


def _batch_size() -> int:
    raw = os.getenv("SENTIMENT_BATCH_SIZE", "32")
    try:
        size = int(raw)
    except ValueError as exc:
        raise RuntimeError("SENTIMENT_BATCH_SIZE must be an integer.") from exc
    if size < 1:
        raise RuntimeError("SENTIMENT_BATCH_SIZE must be at least 1.")
    return size


def _device() -> int:
    requested = os.getenv("SENTIMENT_DEVICE", "cpu").strip().lower()
    if requested in {"cpu", "-1"}:
        return -1
    if requested == "cuda":
        return 0
    raise RuntimeError("SENTIMENT_DEVICE must be 'cpu' or 'cuda'.")
