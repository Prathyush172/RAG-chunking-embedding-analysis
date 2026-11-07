"""
chunkers/__init__.py — Public registry of all chunking strategies.

Add a new chunker by:
1. Creating a module in this package implementing BaseChunker.
2. Importing and registering it here in CHUNKER_REGISTRY.
"""
from __future__ import annotations

from .base import BaseChunker, Chunk, ChunkResult, count_tokens, get_tokenizer
from .fixed import FixedChunker
from .sentence import SentenceChunker
from .semantic import SemanticChunker

# Registry: strategy name -> class
CHUNKER_REGISTRY: dict[str, type[BaseChunker]] = {
    "fixed": FixedChunker,
    "sentence": SentenceChunker,
    "semantic": SemanticChunker,
}


def build_chunker(strategy: str, **kwargs) -> BaseChunker:
    """
    Instantiate a chunker by strategy name.

    Args:
        strategy: One of "fixed", "sentence", "semantic".
        **kwargs: Passed to the chunker constructor.

    Raises:
        ValueError if the strategy is not registered.
    """
    if strategy not in CHUNKER_REGISTRY:
        raise ValueError(
            f"Unknown chunking strategy {strategy!r}. "
            f"Available: {sorted(CHUNKER_REGISTRY)}"
        )
    return CHUNKER_REGISTRY[strategy](**kwargs)


__all__ = [
    "BaseChunker",
    "Chunk",
    "ChunkResult",
    "FixedChunker",
    "SentenceChunker",
    "SemanticChunker",
    "CHUNKER_REGISTRY",
    "build_chunker",
    "count_tokens",
    "get_tokenizer",
]
