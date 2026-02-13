from __future__ import annotations

from dataclasses import dataclass
import math
import os
import re
from typing import Protocol

from rag.index.embeddings import embed_text as _deterministic_hash_embedding


TEST_EMBEDDING_MODE = "test"
PRODUCTION_EMBEDDING_MODE = "production"

DETERMINISTIC_FIXTURE_BACKEND = "deterministic/hash-fixture"
LOCAL_TOKEN_SIGNATURE_BACKEND = "local/token-signature"
LOCAL_CHAR_TRIGRAM_BACKEND = "local/char-trigram"
OPENAI_TEXT_EMBEDDING_3_SMALL_BACKEND = "openai/text-embedding-3-small"

_LOCAL_BACKEND_IDS = (
    LOCAL_TOKEN_SIGNATURE_BACKEND,
    LOCAL_CHAR_TRIGRAM_BACKEND,
)
_OPTIONAL_API_BACKEND_IDS = (OPENAI_TEXT_EMBEDDING_3_SMALL_BACKEND,)

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+")
_LETTER_ORDER = tuple(chr(code) for code in range(ord("a"), ord("z") + 1))
_VOWELS = frozenset({"a", "e", "i", "o", "u"})
_TOKEN_FEATURE_TERMS = (
    "agent",
    "api",
    "artifact",
    "audit",
    "build",
    "chunk",
    "contract",
    "debug",
    "dispatch",
    "embedding",
    "error",
    "evidence",
    "fix",
    "index",
    "langgraph",
    "orchestrator",
    "plan",
    "policy",
    "rag",
    "release",
    "retrieval",
    "runtime",
    "state",
    "test",
    "verify",
)
_COMMON_TRIGRAMS = (
    " the",
    "and",
    "ing",
    "ion",
    "ent",
    "ati",
    "for",
    "tio",
    "ers",
    "ter",
    "all",
    "sth",
    "ver",
    "res",
    "pro",
    "com",
    "int",
    "tri",
    "con",
    "ive",
    "ful",
    "run",
    "log",
    "err",
    "fix",
    "rag",
    "emb",
    "api",
    "sta",
    "pol",
    "tes",
    "pla",
    "dis",
    "cho",
    "gra",
    "ind",
    "ure",
    "de ",
    " re",
    " to",
    " of",
)


class EmbeddingProvider(Protocol):
    name: str
    mode: str
    dimensions: int
    deterministic: bool

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        ...


@dataclass(frozen=True)
class EmbeddingProviderConfig:
    mode: str = TEST_EMBEDDING_MODE
    backend: str | None = None
    dimensions: int = 64
    allow_fallback: bool = True
    openai_model: str = "text-embedding-3-small"


@dataclass(frozen=True)
class DeterministicHashEmbeddingProvider:
    dimensions: int = 64

    name: str = DETERMINISTIC_FIXTURE_BACKEND
    mode: str = TEST_EMBEDDING_MODE
    deterministic: bool = True

    def __post_init__(self) -> None:
        _validate_dimensions(self.dimensions)

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        normalized = _normalize_text_batch(texts)
        return [
            _deterministic_hash_embedding(text, dimensions=self.dimensions)
            for text in normalized
        ]


@dataclass(frozen=True)
class LocalTokenSignatureEmbeddingProvider:
    dimensions: int = 64

    name: str = LOCAL_TOKEN_SIGNATURE_BACKEND
    mode: str = PRODUCTION_EMBEDDING_MODE
    deterministic: bool = True

    def __post_init__(self) -> None:
        _validate_dimensions(self.dimensions)

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        normalized = _normalize_text_batch(texts)
        return [self._embed_single(text) for text in normalized]

    def _embed_single(self, text: str) -> tuple[float, ...]:
        normalized_text = text.lower()
        tokens = _TOKEN_PATTERN.findall(normalized_text)
        if not tokens:
            return _zero_vector(self.dimensions)

        token_count = len(tokens)
        token_lengths = [len(token) for token in tokens]
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1

        alpha_count = sum(1 for ch in normalized_text if ch.isalpha())
        digit_count = sum(1 for ch in normalized_text if ch.isdigit())
        whitespace_count = sum(1 for ch in normalized_text if ch.isspace())
        text_length = max(len(normalized_text), 1)
        punctuation_count = max(text_length - alpha_count - digit_count - whitespace_count, 0)
        vowel_count = sum(1 for ch in normalized_text if ch in _VOWELS)

        token_count_float = float(token_count)
        features: list[float] = [
            math.log1p(token_count_float),
            len(counts) / token_count_float,
            sum(token_lengths) / token_count_float / 24.0,
            max(token_lengths) / 24.0,
            sum(1 for token in tokens if any(ch.isdigit() for ch in token)) / token_count_float,
            sum(1 for token in tokens if "_" in token) / token_count_float,
            alpha_count / text_length,
            digit_count / text_length,
            whitespace_count / text_length,
            punctuation_count / text_length,
            vowel_count / max(alpha_count, 1),
            len(tokens[0]) / 24.0,
            len(tokens[-1]) / 24.0,
        ]

        features.extend(_token_length_buckets(token_lengths))
        features.extend(_letter_frequency_features(normalized_text, alpha_count=alpha_count))
        features.extend(counts.get(term, 0) / token_count_float for term in _TOKEN_FEATURE_TERMS)

        dense = list(_fit_dimensions(features, dimensions=self.dimensions))
        return _normalized_vector(dense)


@dataclass(frozen=True)
class LocalCharTrigramEmbeddingProvider:
    dimensions: int = 64

    name: str = LOCAL_CHAR_TRIGRAM_BACKEND
    mode: str = PRODUCTION_EMBEDDING_MODE
    deterministic: bool = True

    def __post_init__(self) -> None:
        _validate_dimensions(self.dimensions)

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        normalized = _normalize_text_batch(texts)
        return [self._embed_single(text) for text in normalized]

    def _embed_single(self, text: str) -> tuple[float, ...]:
        compact = re.sub(r"\s+", " ", text.lower()).strip()
        if not compact:
            return _zero_vector(self.dimensions)

        padded = f" {compact} "
        if len(padded) < 3:
            grams = [padded]
        else:
            grams = [padded[index : index + 3] for index in range(len(padded) - 2)]

        gram_total = max(len(grams), 1)
        gram_counts: dict[str, int] = {}
        for gram in grams:
            gram_counts[gram] = gram_counts.get(gram, 0) + 1

        features = [gram_counts.get(gram, 0) / gram_total for gram in _COMMON_TRIGRAMS]

        alpha_count = sum(1 for ch in compact if ch.isalpha())
        digit_count = sum(1 for ch in compact if ch.isdigit())
        whitespace_count = sum(1 for ch in compact if ch.isspace())
        punctuation_count = max(len(compact) - alpha_count - digit_count - whitespace_count, 0)
        text_length = max(len(compact), 1)
        features.extend(
            [
                alpha_count / text_length,
                digit_count / text_length,
                whitespace_count / text_length,
                punctuation_count / text_length,
            ]
        )
        features.extend(_vowel_consonant_transition_features(compact))

        dense = list(_fit_dimensions(features, dimensions=self.dimensions))
        return _normalized_vector(dense)


@dataclass(frozen=True)
class OpenAIEmbeddingProvider:
    dimensions: int = 1536
    model: str = "text-embedding-3-small"

    name: str = OPENAI_TEXT_EMBEDDING_3_SMALL_BACKEND
    mode: str = PRODUCTION_EMBEDDING_MODE
    deterministic: bool = False

    def __post_init__(self) -> None:
        _validate_dimensions(self.dimensions)

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        normalized = _normalize_text_batch(texts)
        if not normalized:
            return []

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embedding backend")

        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("openai package is required for OpenAI embedding backend") from exc

        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model=self.model, input=normalized)
        vectors: list[tuple[float, ...]] = []
        for item in response.data:
            raw = [float(value) for value in item.embedding]
            vectors.append(_fit_dimensions(raw, dimensions=self.dimensions))
        return vectors


def local_embedding_candidates() -> tuple[str, ...]:
    return _LOCAL_BACKEND_IDS


def optional_api_embedding_candidates() -> tuple[str, ...]:
    return _OPTIONAL_API_BACKEND_IDS


def build_embedding_provider(config: EmbeddingProviderConfig | None = None) -> EmbeddingProvider:
    effective = config or EmbeddingProviderConfig()
    mode = _normalize_mode(effective.mode)
    dimensions = int(effective.dimensions)
    _validate_dimensions(dimensions)

    if mode == TEST_EMBEDDING_MODE:
        return DeterministicHashEmbeddingProvider(dimensions=dimensions)

    backend = _normalize_backend(effective.backend) or LOCAL_TOKEN_SIGNATURE_BACKEND

    local_factories = {
        LOCAL_TOKEN_SIGNATURE_BACKEND: lambda: LocalTokenSignatureEmbeddingProvider(
            dimensions=dimensions
        ),
        LOCAL_CHAR_TRIGRAM_BACKEND: lambda: LocalCharTrigramEmbeddingProvider(dimensions=dimensions),
        DETERMINISTIC_FIXTURE_BACKEND: lambda: DeterministicHashEmbeddingProvider(dimensions=dimensions),
    }

    if backend in local_factories:
        return local_factories[backend]()

    if backend == OPENAI_TEXT_EMBEDDING_3_SMALL_BACKEND:
        if _openai_backend_available():
            return OpenAIEmbeddingProvider(
                dimensions=dimensions,
                model=effective.openai_model,
            )
        if effective.allow_fallback:
            return LocalTokenSignatureEmbeddingProvider(dimensions=dimensions)
        raise RuntimeError(
            "OpenAI embedding backend is unavailable (missing openai package or OPENAI_API_KEY)"
        )

    supported = ", ".join(
        sorted(
            {
                DETERMINISTIC_FIXTURE_BACKEND,
                *local_embedding_candidates(),
                *optional_api_embedding_candidates(),
            }
        )
    )
    raise ValueError(f"unsupported embedding backend '{backend}'. Supported values: {supported}")


def _validate_dimensions(dimensions: int) -> None:
    if dimensions <= 0:
        raise ValueError("dimensions must be > 0")


def _normalize_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in {TEST_EMBEDDING_MODE, PRODUCTION_EMBEDDING_MODE}:
        raise ValueError("mode must be 'test' or 'production'")
    return mode


def _normalize_backend(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_text_batch(texts: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in texts:
        if not isinstance(value, str):
            raise TypeError("embedding input texts must be strings")
        normalized.append(value)
    return normalized


def _zero_vector(dimensions: int) -> tuple[float, ...]:
    return tuple(0.0 for _ in range(dimensions))


def _token_length_buckets(lengths: list[int]) -> list[float]:
    if not lengths:
        return [0.0] * 8

    buckets = [0.0] * 8
    for length in lengths:
        if length <= 1:
            buckets[0] += 1.0
        elif length == 2:
            buckets[1] += 1.0
        elif length == 3:
            buckets[2] += 1.0
        elif length == 4:
            buckets[3] += 1.0
        elif length == 5:
            buckets[4] += 1.0
        elif length <= 8:
            buckets[5] += 1.0
        elif length <= 12:
            buckets[6] += 1.0
        else:
            buckets[7] += 1.0
    total = float(len(lengths))
    return [value / total for value in buckets]


def _letter_frequency_features(text: str, *, alpha_count: int) -> list[float]:
    if alpha_count <= 0:
        return [0.0] * len(_LETTER_ORDER)

    counts = {letter: 0 for letter in _LETTER_ORDER}
    for ch in text:
        if ch in counts:
            counts[ch] += 1
    divisor = float(alpha_count)
    return [counts[letter] / divisor for letter in _LETTER_ORDER]


def _vowel_consonant_transition_features(text: str) -> list[float]:
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 2:
        return [0.0, 0.0, 0.0, 0.0]

    transitions = [0.0, 0.0, 0.0, 0.0]  # vv, vc, cv, cc
    for first, second in zip(letters, letters[1:]):
        first_vowel = first in _VOWELS
        second_vowel = second in _VOWELS
        if first_vowel and second_vowel:
            transitions[0] += 1.0
        elif first_vowel and not second_vowel:
            transitions[1] += 1.0
        elif not first_vowel and second_vowel:
            transitions[2] += 1.0
        else:
            transitions[3] += 1.0
    total = sum(transitions) or 1.0
    return [value / total for value in transitions]


def _normalized_vector(values: list[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return tuple(0.0 for _ in values)
    return tuple(round(value / norm, 8) for value in values)


def _fit_dimensions(values: list[float], *, dimensions: int) -> tuple[float, ...]:
    if len(values) == dimensions:
        return tuple(values)
    if len(values) > dimensions:
        return tuple(values[:dimensions])
    if len(values) < dimensions:
        padded = list(values)
        padded.extend([0.0] * (dimensions - len(values)))
        return tuple(padded)
    return tuple(values)


def _openai_backend_available() -> bool:
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    try:
        import openai  # noqa: F401
    except Exception:
        return False
    return True
