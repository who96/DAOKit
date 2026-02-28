"""RAG module for DAOKit with Chroma vector database support."""

__all__ = ["RAGEngine", "split_text"]


def __getattr__(name: str):
    if name in ("RAGEngine", "split_text"):
        from rag.engine import RAGEngine, split_text

        globals()["RAGEngine"] = RAGEngine
        globals()["split_text"] = split_text
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
