"""Text embedders. Local and free by default; swap in a hosted model by writing another class.

The vector column is fixed at 384 dimensions (migration 004). Changing to a model with a
different size means a new migration and re-indexing.
"""
from typing import Protocol

DIM = 384
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    dim = DIM

    def __init__(self, model: str = DEFAULT_MODEL):
        from fastembed import TextEmbedding  # heavy import, load on use

        self.name = model
        self._model = TextEmbedding(model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()
