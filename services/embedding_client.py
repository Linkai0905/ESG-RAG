# services/embedding_client.py
from __future__ import annotations

from typing import List, Any

from openai import OpenAI

from config import (
    EMBEDDING_PROVIDER,
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    EMBEDDING_PASS_DIMENSIONS,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_ENCODING_FORMAT,
)


def get_embedding_client() -> OpenAI:
    if EMBEDDING_PROVIDER != "openai_compatible":
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")

    if not EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY is missing")

    if not EMBEDDING_BASE_URL:
        raise RuntimeError("EMBEDDING_BASE_URL is missing")

    if not EMBEDDING_MODEL:
        raise RuntimeError("EMBEDDING_MODEL is missing")

    return OpenAI(
        api_key=EMBEDDING_API_KEY,
        base_url=EMBEDDING_BASE_URL,
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    clean_texts = [_normalize_text(x) for x in texts]

    client = get_embedding_client()
    all_embeddings: List[List[float]] = []

    batch_size = max(1, min(EMBEDDING_BATCH_SIZE, 100))

    for i in range(0, len(clean_texts), batch_size):
        batch = clean_texts[i:i + batch_size]
        all_embeddings.extend(_embed_batch(client, batch))

    return all_embeddings


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]


def _embed_batch(client: OpenAI, batch: List[str]) -> List[List[float]]:
    kwargs: dict[str, Any] = {
        "model": EMBEDDING_MODEL,
        "input": batch,
    }

    if EMBEDDING_ENCODING_FORMAT:
        kwargs["encoding_format"] = EMBEDDING_ENCODING_FORMAT

    # 不默认传 dimensions。
    # 只有 .env 里 EMBEDDING_PASS_DIMENSIONS=true 且 EMBEDDING_DIM 有值时才传。
    if EMBEDDING_PASS_DIMENSIONS and EMBEDDING_DIM:
        kwargs["dimensions"] = EMBEDDING_DIM

    try:
        resp = client.embeddings.create(**kwargs)
    except Exception as e:
        # 有些 OpenAI-compatible embedding 服务不支持 dimensions。
        # 如果传了 dimensions 报错，自动去掉 dimensions 重试一次。
        if "dimensions" in kwargs:
            kwargs.pop("dimensions", None)
            resp = client.embeddings.create(**kwargs)
        else:
            raise e

    data = sorted(resp.data, key=lambda x: x.index)
    return [x.embedding for x in data]


def _normalize_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
    text = " ".join(text.split())

    # Demo 阶段字符级截断，避免网页正文异常超长。
    # 正常 chunker 已经切到 800 字左右，这里只是兜底。
    return text[:6000]