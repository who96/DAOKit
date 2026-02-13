from __future__ import annotations

from dataclasses import dataclass
import unittest

from rag.index.providers import (
    EmbeddingProvider,
    EmbeddingProviderConfig,
    LOCAL_TOKEN_SIGNATURE_BACKEND,
    build_embedding_provider,
    local_embedding_candidates,
    optional_api_embedding_candidates,
)
from rag.index.store import ChunkForIndex, EmbeddingIndexStore


@dataclass
class _RecordingProvider(EmbeddingProvider):
    dimensions: int
    name: str = "recording-fixture"
    mode: str = "test"
    deterministic: bool = True

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        self.calls.append(tuple(texts))
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            if "alpha" in text.lower():
                vectors.append((1.0, 0.0, 0.0, 0.0))
            elif "beta" in text.lower():
                vectors.append((0.0, 1.0, 0.0, 0.0))
            else:
                vectors.append((0.0, 0.0, 1.0, 0.0))
        return vectors


class EmbeddingProviderTests(unittest.TestCase):
    def test_index_search_uses_embedding_provider_abstraction(self) -> None:
        provider = _RecordingProvider(dimensions=4)
        chunks = [
            ChunkForIndex(
                chunk_id="alpha-1",
                text="alpha planning note",
                source_path="docs/a.md",
                source_type="markdown",
                task_id="DKT-059",
                run_id="RUN-A",
                chunk_index=0,
                total_chunks=1,
            ),
            ChunkForIndex(
                chunk_id="beta-1",
                text="beta troubleshooting note",
                source_path="docs/b.md",
                source_type="markdown",
                task_id="DKT-059",
                run_id="RUN-A",
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        store = EmbeddingIndexStore.from_chunks(chunks, dimensions=4, embedding_provider=provider)
        self.assertGreaterEqual(len(provider.calls), 1)

        provider.calls.clear()
        hits = store.search("alpha", top_k=1)

        self.assertEqual(provider.calls, [("alpha",)])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk_id, "alpha-1")

    def test_test_mode_provider_is_deterministic_hash_fixture(self) -> None:
        provider = build_embedding_provider(
            EmbeddingProviderConfig(mode="test", backend=None, dimensions=16)
        )
        self.assertTrue(provider.deterministic)
        self.assertIn("deterministic", provider.name)

        first = provider.embed_texts(["same input"])[0]
        second = provider.embed_texts(["same input"])[0]
        self.assertEqual(first, second)

    def test_production_mode_supports_local_candidates_and_optional_api(self) -> None:
        local_candidates = local_embedding_candidates()
        api_candidates = optional_api_embedding_candidates()

        self.assertGreaterEqual(len(local_candidates), 2)
        self.assertGreaterEqual(len(api_candidates), 1)

        provider = build_embedding_provider(
            EmbeddingProviderConfig(
                mode="production",
                backend=local_candidates[0],
                dimensions=32,
            )
        )
        self.assertEqual(provider.dimensions, 32)
        self.assertIn(provider.name, set(local_candidates))

    def test_unavailable_api_provider_falls_back_to_local_candidate(self) -> None:
        provider = build_embedding_provider(
            EmbeddingProviderConfig(
                mode="production",
                backend="openai/text-embedding-3-small",
                dimensions=24,
                allow_fallback=True,
            )
        )
        self.assertIn(provider.name, set(local_embedding_candidates()))
        self.assertEqual(provider.dimensions, 24)

    def test_local_token_signature_provider_vector_signature_is_stable(self) -> None:
        provider = build_embedding_provider(
            EmbeddingProviderConfig(
                mode="production",
                backend=LOCAL_TOKEN_SIGNATURE_BACKEND,
                dimensions=16,
            )
        )
        vector = provider.embed_texts(
            ["Production retrieval should use provider-backed vectors, not hash fixtures."]
        )[0]
        self.assertEqual(
            vector,
            (
                0.83732383,
                0.34919116,
                0.09311764,
                0.14549632,
                0.0,
                0.0,
                0.29797645,
                0.0,
                0.03724706,
                0.01396765,
                0.13094668,
                0.14549632,
                0.11639705,
                0.0,
                0.0,
                0.06983823,
            ),
        )


if __name__ == "__main__":
    unittest.main()
