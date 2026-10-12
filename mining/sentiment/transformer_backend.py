"""Optional Hugging Face sentiment backend.

Nothing here downloads or loads a model unless ``SENTIMENT_MODEL=transformer``.
The default VADER path does not import ``transformers`` or ``torch``.

The default model is ``cardiffnlp/twitter-roberta-base-sentiment-latest``.
Its published config maps class 0 to negative, 1 to neutral, and 2 to positive.
Those names are read from the loaded config. They are not guessed from
``LABEL_0`` style ids. The model card describes an English Twitter RoBERTa,
not a multilingual or restaurant-specific model.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

from mining.sentiment.preprocess import clean_text
from mining.sentiment.vader_baseline import SentimentScore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
FOODPULSE_LABELS = frozenset({"positive", "negative", "neutral"})
_CACHE: dict[tuple[str, str], "TransformerClassifier"] = {}


@dataclass
class TransformerClassifier:
    """One loaded model, reused for every later batch with the same settings."""

    model_name: str
    device_name: str
    id2label: dict[int, str]
    tokenizer: object
    model: object
    torch: object
    max_length: int

    def predict(self, texts: list[str]) -> list[tuple[str, float]]:
        """Return ``(label, confidence)`` for each non-empty text."""
        if not texts:
            return []
        self.model.eval()
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = {name: tensor.to(self.model.device) for name, tensor in encoded.items()}
        with self.torch.no_grad():
            logits = self.model(**encoded).logits
        if logits.shape[0] != len(texts):
            raise RuntimeError("Transformer returned a different number of predictions than texts.")
        probabilities = self.torch.softmax(logits, dim=-1)
        chosen = probabilities.argmax(dim=-1)
        rows: list[tuple[str, float]] = []
        for row_index, class_index in enumerate(chosen.tolist()):
            if class_index not in self.id2label:
                raise RuntimeError(f"Transformer predicted unknown class index {class_index}.")
            confidence = float(probabilities[row_index, class_index].item())
            if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
                raise RuntimeError("Transformer confidence was outside the range 0 to 1.")
            rows.append((self.id2label[class_index], confidence))
        return rows


def selected_backend() -> str:
    """Return ``vader`` or ``transformer``. Any other value is an error."""
    raw = os.getenv("SENTIMENT_MODEL", "vader")
    value = raw.strip().lower()
    if value not in {"vader", "transformer"}:
        raise RuntimeError(f"SENTIMENT_MODEL must be 'vader' or 'transformer'. Received {raw!r}.")
    return value


def transformer_selected() -> bool:
    """Return True only when the transformer backend was explicitly requested."""
    return selected_backend() == "transformer"


def score_texts(texts: list[object]) -> list[SentimentScore]:
    """Score a batch. Empty text is invalid and is not sent to the model."""
    if selected_backend() != "transformer":
        raise RuntimeError(
            "Transformer sentiment is not selected. Set SENTIMENT_MODEL=transformer "
            "to load it. The default backend is VADER and does not download a model."
        )
    pending: list[str] = []
    pending_indexes: list[int] = []
    results: list[SentimentScore | None] = []
    for index, value in enumerate(texts):
        cleaned = clean_text(value)
        if not cleaned:
            results.append(SentimentScore(label="invalid", compound=None, confidence=None, backend="transformer"))
            continue
        results.append(None)
        pending.append(cleaned)
        pending_indexes.append(index)
    if not pending:
        return [item for item in results if item is not None]
    batch_size = _batch_size()
    classifier = get_classifier()
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        predictions = classifier.predict(chunk)
        if len(predictions) != len(chunk):
            raise RuntimeError("Transformer batch size did not match the number of texts.")
        for offset, (label, confidence) in enumerate(predictions):
            if label not in FOODPULSE_LABELS:
                raise RuntimeError(f"Transformer label {label!r} is not positive, negative, or neutral.")
            if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
                raise RuntimeError("Transformer confidence was outside the range 0 to 1.")
            results[pending_indexes[start + offset]] = SentimentScore(
                label=label,
                compound=_signed_confidence(label, confidence),
                confidence=confidence,
                backend="transformer",
            )
    if any(item is None for item in results):
        raise RuntimeError("Transformer scoring left a review without a prediction.")
    return [item for item in results if item is not None]


def map_id2label(id2label: dict[object, object]) -> dict[int, str]:
    """Map a loaded config's labels onto positive, negative, and neutral."""
    mapped: dict[int, str] = {}
    for key, raw_label in id2label.items():
        label = str(raw_label).strip().lower()
        if label not in FOODPULSE_LABELS:
            raise RuntimeError(
                f"Model label {raw_label!r} is not one of positive, negative, or neutral. "
                "Refusing to guess a FoodPulse label."
            )
        mapped[int(key)] = label
    if set(mapped.values()) != FOODPULSE_LABELS:
        found = ", ".join(sorted(set(mapped.values()))) or "(none)"
        raise RuntimeError(f"Model config must contain positive, negative, and neutral. Found: {found}.")
    return mapped


def get_classifier() -> TransformerClassifier:
    """Load the configured model once per process, model id, and device."""
    model_name = os.getenv("SENTIMENT_TRANSFORMER_MODEL", DEFAULT_MODEL).strip()
    if not model_name:
        raise RuntimeError("SENTIMENT_TRANSFORMER_MODEL is empty, so no model will be loaded.")
    device_name = _device_name()
    key = (model_name, device_name)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    loaded = _load_classifier(model_name, device_name)
    _CACHE[key] = loaded
    return loaded


def clear_classifier_cache() -> None:
    """Drop the cached model. Tests use this so one case cannot leak into another."""
    _CACHE.clear()


def _load_classifier(model_name: str, device_name: str) -> TransformerClassifier:
    try:
        torch, auto_config, auto_model, auto_tokenizer = _import_runtime()
    except ImportError as exc:
        raise RuntimeError(
            "SENTIMENT_MODEL=transformer but torch or transformers is not installed. "
            "The default VADER path does not need either package."
        ) from exc
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("SENTIMENT_DEVICE=cuda but CUDA is not available. Set SENTIMENT_DEVICE=cpu.")
    logger.info("Loading transformer %s on %s", model_name, device_name)
    try:
        config = auto_config.from_pretrained(model_name)
        id2label = map_id2label(dict(config.id2label))
        tokenizer = auto_tokenizer.from_pretrained(model_name)
        model = auto_model.from_pretrained(model_name)
        model.to(device_name)
        model.eval()
    except Exception as exc:
        raise RuntimeError(f"Could not load transformer model {model_name!r} on {device_name}.") from exc
    return TransformerClassifier(
        model_name=model_name,
        device_name=device_name,
        id2label=id2label,
        tokenizer=tokenizer,
        model=model,
        torch=torch,
        max_length=_max_length(tokenizer, config),
    )


def _import_runtime():
    try:
        import torch
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "SENTIMENT_MODEL=transformer but torch or transformers is not installed. "
            "The default VADER path does not need either package."
        ) from exc
    return torch, AutoConfig, AutoModelForSequenceClassification, AutoTokenizer


def _signed_confidence(label: str, confidence: float) -> float:
    """Keep a signed score for callers that still read ``compound``."""
    if label == "positive":
        return confidence
    if label == "negative":
        return -confidence
    return 0.0


def _batch_size() -> int:
    raw = os.getenv("SENTIMENT_BATCH_SIZE", "16")
    try:
        size = int(raw)
    except ValueError as exc:
        raise RuntimeError("SENTIMENT_BATCH_SIZE must be an integer.") from exc
    if size < 1:
        raise RuntimeError("SENTIMENT_BATCH_SIZE must be at least 1.")
    return size


def _device_name() -> str:
    requested = os.getenv("SENTIMENT_DEVICE", "cpu").strip().lower()
    if requested in {"cpu", "-1"}:
        return "cpu"
    if requested == "cuda":
        return "cuda"
    raise RuntimeError("SENTIMENT_DEVICE must be 'cpu' or 'cuda'.")


def _max_length(tokenizer: object, config: object) -> int:
    limit = getattr(tokenizer, "model_max_length", 512)
    if not isinstance(limit, int) or limit > 10_000:
        limit = 512
    positions = int(getattr(config, "max_position_embeddings", 512))
    usable = positions - 2 if positions > 2 else positions
    return max(8, min(limit, usable))
