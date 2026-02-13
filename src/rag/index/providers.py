from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
        tokens = _TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            return _zero_vector(self.dimensions)

        vector = [0.0] * self.dimensions
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1

        for token, count in counts.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], byteorder="big") % self.dimensions
            length_weight = 1.0 + min(len(token), 24) / 24.0
            frequency_weight = 1.0 + math.log1p(count)
            vector[index] += length_weight * frequency_weight

        return _normalized_vector(vector)


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

        if len(compact) < 3:
            grams = [compact]
        else:
            grams = [compact[index : index + 3] for index in range(len(compact) - 2)]

        vector = [0.0] * self.dimensions
        for gram in grams:
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], byteorder="big") % self.dimensions
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            magnitude = (digest[3] + 1) / 256.0
            vector[index] += sign * magnitude

        return _normalized_vector(vector)


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
