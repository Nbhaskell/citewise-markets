"""Things each request needs, as FastAPI dependencies so tests can replace them with fakes."""
from functools import lru_cache
from typing import Iterator

import psycopg
from fastapi import HTTPException

from ai.embeddings import Embedder, FastEmbedder
from ai.llm import LLM, get_llm
from data.db import connect, get_setting

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
)


def get_conn() -> Iterator[psycopg.Connection]:
    try:
        conn = connect()
    except psycopg.OperationalError as exc:
        raise HTTPException(503, "The database isn't reachable. Is Docker running?") from exc
    try:
        yield conn
    finally:
        conn.close()


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return FastEmbedder()  # loaded on the first search or copilot request, then reused


@lru_cache(maxsize=1)
def get_chat_model() -> LLM:
    return get_llm()


def get_sentiment_model() -> str:
    """Name of the model whose headline labels the API reports."""
    return get_chat_model().name


def cors_origins() -> list[str]:
    return [o.strip() for o in (get_setting("CORS_ORIGINS") or DEFAULT_CORS_ORIGINS).split(",") if o.strip()]
