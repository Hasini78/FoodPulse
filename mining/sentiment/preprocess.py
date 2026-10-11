"""Offline review-text preprocessing.

spaCy and NLTK are used when they are already installed and their language
data is present. Otherwise a local tokenizer and lemmatizer run with no
download. Negations, contrast words, and punctuation are kept.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

NEGATION_WORDS = frozenset({"not", "never", "no", "nor", "without", "n't", "cannot"})
CONTRAST_WORDS = frozenset({"but", "however", "although", "though", "yet", "while"})
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9']+|[^\w\s]", re.IGNORECASE)
_CONTRACTION_RE = re.compile(r"n't$")
_IRREGULAR = {
    "was": "be",
    "were": "be",
    "is": "be",
    "are": "be",
    "been": "be",
    "has": "have",
    "had": "have",
    "did": "do",
    "prices": "price",
    "flavors": "flavor",
    "flavours": "flavour",
    "servers": "server",
}


@dataclass(frozen=True)
class PreparedText:
    """Clean text plus tokens and lemmas."""

    text: str
    tokens: tuple[str, ...]
    lemmas: tuple[str, ...]


def clean_text(value: object) -> str:
    """Strip HTML and collapse whitespace. Empty input becomes an empty string."""
    if value is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = html.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip().lower()
    return text


def tokenize(text: str) -> tuple[str, ...]:
    """Split text into word and punctuation tokens."""
    return tuple(token.lower() for token in _TOKEN_RE.findall(text))


def lemmatize_token(token: str) -> str:
    """Lemmatize one token without dropping negations or punctuation."""
    if not token.isalpha():
        return token
    if token in NEGATION_WORDS or token in CONTRAST_WORDS:
        return token
    if token in _IRREGULAR:
        return _IRREGULAR[token]
    nltk_lemma = _nltk_lemma(token)
    if nltk_lemma:
        return nltk_lemma
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) > 4 and not token.endswith("ss"):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def prepare_text(value: object) -> PreparedText:
    """Clean, tokenize, and lemmatize one review."""
    text = clean_text(value)
    if not text:
        return PreparedText(text="", tokens=(), lemmas=())
    spacy_lemmas = _spacy_lemmas(text)
    if spacy_lemmas is not None:
        tokens = tokenize(text)
        return PreparedText(text=text, tokens=tokens, lemmas=spacy_lemmas)
    tokens = tokenize(text)
    lemmas = tuple(_expand_negation(lemmatize_token(token)) for token in tokens)
    return PreparedText(text=text, tokens=tokens, lemmas=lemmas)


def split_clauses(text: str) -> tuple[str, ...]:
    """Split on sentence boundaries and contrast words such as ``but``."""
    if not text:
        return ()
    parts = re.split(r"\b(?:but|however|although|though|yet|while)\b|[.!;?]", text, flags=re.IGNORECASE)
    return tuple(part.strip(" ,") for part in parts if part.strip(" ,"))


def _expand_negation(token: str) -> str:
    if _CONTRACTION_RE.search(token):
        return "not"
    return token


def _nltk_lemma(token: str) -> str | None:
    lemmatizer = _wordnet_lemmatizer()
    if lemmatizer is None:
        return None
    try:
        return str(lemmatizer.lemmatize(token))
    except LookupError:
        return None


def _wordnet_lemmatizer():
    global _NLTK_LEM
    if _NLTK_LEM is False:
        return None
    if _NLTK_LEM is not None:
        return _NLTK_LEM
    try:
        from nltk.stem import WordNetLemmatizer

        lemmatizer = WordNetLemmatizer()
        lemmatizer.lemmatize("prices")
        _NLTK_LEM = lemmatizer
        logger.info("Using NLTK WordNet lemmatizer")
    except Exception:
        _NLTK_LEM = False
        logger.info("NLTK WordNet data is unavailable; using the offline lemmatizer")
        return None
    return _NLTK_LEM


def _spacy_lemmas(text: str) -> tuple[str, ...] | None:
    """Use spaCy lemmas when a local English model is already installed."""
    nlp = _spacy_model()
    if nlp is None:
        return None
    doc = nlp(text)
    lemmas: list[str] = []
    for token in doc:
        if token.is_space:
            continue
        if token.is_punct:
            lemmas.append(token.text.lower())
            continue
        lemma = token.lemma_.lower()
        if token.dep_ == "neg" or lemma in NEGATION_WORDS:
            lemmas.append("not")
        else:
            lemmas.append(lemma)
    return tuple(lemmas)


def _spacy_model():
    global _SPACY
    if _SPACY is False:
        return None
    if _SPACY is not None:
        return _SPACY
    try:
        import spacy

        _SPACY = spacy.load("en_core_web_sm")
        logger.info("Using spaCy model en_core_web_sm")
    except Exception:
        _SPACY = False
        logger.info("spaCy English model is unavailable; using the offline tokenizer")
        return None
    return _SPACY


_NLTK_LEM = None
_SPACY = None
