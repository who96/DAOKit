from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from chromadb import Documents, Embeddings
    from chromadb.api.types import EmbeddingFunction

    _HAS_CHROMADB = True
except ImportError:
    _HAS_CHROMADB = False

_SKIP_REASON = "chromadb is not installed"

if _HAS_CHROMADB:

    class _DeterministicEF(EmbeddingFunction[Documents]):  # type: ignore[type-arg]
        """Hash-based embedding function that needs no network access."""

        def __init__(self) -> None:
            pass

        def __call__(self, input: Documents) -> Embeddings:
            return [self._embed(t) for t in input]

        @staticmethod
        def name() -> str:
            return "test_deterministic_hash"

        def get_config(self) -> dict:
            return {}

        @staticmethod
        def build_from_config(config: dict) -> "_DeterministicEF":
            return _DeterministicEF()

        @staticmethod
        def _embed(text: str) -> list[float]:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h]
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            return [x / norm for x in vec]


@unittest.skipUnless(_HAS_CHROMADB, _SKIP_REASON)
class RAGEngineTests(unittest.TestCase):
    """Integration tests for the Chroma-backed RAGEngine."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._ef = _DeterministicEF()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def _make_engine(self, collection: str = "test"):
        from rag.engine import RAGEngine

        return RAGEngine(
            collection_name=collection,
            persist_dir=self._tmpdir,
            embedding_function=self._ef,
        )

    # -- tests ------------------------------------------------------------

    def test_add_and_count(self) -> None:
        engine = self._make_engine()
        self.assertEqual(engine.count, 0)

        added = engine.add_documents(["hello world", "foo bar"])
        self.assertEqual(added, 2)
        self.assertEqual(engine.count, 2)

    def test_add_empty_list(self) -> None:
        engine = self._make_engine()
        self.assertEqual(engine.add_documents([]), 0)
        self.assertEqual(engine.count, 0)

    def test_add_with_metadatas(self) -> None:
        engine = self._make_engine()
        engine.add_documents(
            ["alpha", "beta"],
            metadatas=[{"k": "a"}, {"k": "b"}],
        )
        self.assertEqual(engine.count, 2)

    def test_add_mismatched_metadatas_raises(self) -> None:
        engine = self._make_engine()
        with self.assertRaises(ValueError):
            engine.add_documents(["one"], metadatas=[{"a": 1}, {"b": 2}])

    def test_query_returns_results(self) -> None:
        engine = self._make_engine()
        docs = [
            "Python 是一种广泛使用的编程语言",
            "Java 常用于企业级后端开发",
            "机器学习需要大量的训练数据",
            "深度学习是机器学习的一个分支",
        ]
        engine.add_documents(docs)

        hits = engine.query("编程语言", top_k=2)
        self.assertEqual(len(hits), 2)
        for hit in hits:
            self.assertIn("text", hit)
            self.assertIn("score", hit)
            self.assertIn("metadata", hit)

    def test_query_empty_collection(self) -> None:
        engine = self._make_engine()
        hits = engine.query("anything")
        self.assertEqual(hits, [])

    def test_query_top_k_exceeds_count(self) -> None:
        engine = self._make_engine()
        engine.add_documents(["only one doc"])
        hits = engine.query("one", top_k=10)
        self.assertEqual(len(hits), 1)

    def test_delete_collection(self) -> None:
        engine = self._make_engine(collection="to_delete")
        engine.add_documents(["delete me"])
        self.assertEqual(engine.count, 1)
        engine.delete_collection()

        from rag.engine import RAGEngine

        names = RAGEngine.list_collections(persist_dir=self._tmpdir)
        self.assertNotIn("to_delete", names)

    def test_list_collections(self) -> None:
        self._make_engine(collection="col_a")
        self._make_engine(collection="col_b")

        from rag.engine import RAGEngine

        names = RAGEngine.list_collections(persist_dir=self._tmpdir)
        self.assertIn("col_a", names)
        self.assertIn("col_b", names)

    def test_add_file(self) -> None:
        engine = self._make_engine()
        txt = Path(self._tmpdir) / "sample.txt"
        txt.write_text("这是一段测试文本。" * 200, encoding="utf-8")

        added = engine.add_file(txt, chunk_size=100, chunk_overlap=20)
        self.assertGreater(added, 1)
        self.assertEqual(engine.count, added)

    def test_repr(self) -> None:
        engine = self._make_engine()
        r = repr(engine)
        self.assertIn("RAGEngine", r)
        self.assertIn("test", r)


@unittest.skipUnless(_HAS_CHROMADB, _SKIP_REASON)
class SplitTextTests(unittest.TestCase):
    """Unit tests for the split_text helper."""

    def test_basic_split(self) -> None:
        from rag.engine import split_text

        text = "a" * 100
        chunks = split_text(text, chunk_size=30, chunk_overlap=10)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 30)

    def test_empty_text(self) -> None:
        from rag.engine import split_text

        self.assertEqual(split_text("", chunk_size=10, chunk_overlap=0), [])
        self.assertEqual(split_text("   ", chunk_size=10, chunk_overlap=0), [])

    def test_invalid_params(self) -> None:
        from rag.engine import split_text

        with self.assertRaises(ValueError):
            split_text("hello", chunk_size=0, chunk_overlap=0)
        with self.assertRaises(ValueError):
            split_text("hello", chunk_size=10, chunk_overlap=10)

    def test_no_overlap(self) -> None:
        from rag.engine import split_text

        text = "abcdefghij"
        chunks = split_text(text, chunk_size=5, chunk_overlap=0)
        self.assertEqual(chunks, ["abcde", "fghij"])

    def test_short_text_single_chunk(self) -> None:
        from rag.engine import split_text

        chunks = split_text("short", chunk_size=100, chunk_overlap=10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], "short")


if __name__ == "__main__":
    unittest.main()
