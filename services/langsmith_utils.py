from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def wrap_openai_client(client: T) -> T:
    """
    Wrap OpenAI-compatible clients for LangSmith tracing when langsmith is installed.
    If tracing is disabled or langsmith is unavailable, the original client is returned.
    """
    try:
        from langsmith import wrappers
    except Exception:
        return client

    try:
        return wrappers.wrap_openai(client)  # type: ignore[return-value]
    except Exception:
        return client
