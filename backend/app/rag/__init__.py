"""RAG module exports.

Keep imports lazy so lightweight modules like ``app.rag.chunker`` can be used
without pulling in the full engine and database stack at import time.
"""

from typing import Any


__all__ = ["RAGEngine", "rag_engine"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from app.rag.engine import RAGEngine, rag_engine

        exports = {
            "RAGEngine": RAGEngine,
            "rag_engine": rag_engine,
        }
        return exports[name]
    raise AttributeError(f"module 'app.rag' has no attribute {name!r}")
