# services/chroma_store.py
from __future__ import annotations

from typing import Any

import chromadb

from config import CHROMA_DISTANCE
from schemas import ChunkItem, EvidenceItem, SectionType
from services.embedding_client import embed_texts, embed_query


def get_collection(chroma_path: str, collection_name: str):
    client = chromadb.PersistentClient(path=chroma_path)

    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": CHROMA_DISTANCE},
    )


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean = {}

    for k, v in metadata.items():
        if v is None:
            clean[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)

    return clean


def add_chunks(
    chroma_path: str,
    collection_name: str,
    chunks: list[dict],
) -> None:
    collection = get_collection(chroma_path, collection_name)

    ids = []
    documents = []
    metadatas = []

    for raw in chunks:
        chunk = ChunkItem.model_validate(raw)
        item = chunk.to_chroma()

        ids.append(item["id"])
        documents.append(item["document"])
        metadatas.append(_sanitize_metadata(item["metadata"]))

    if not ids:
        return

    embeddings = embed_texts(documents)

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def retrieve_chunks(
    chroma_path: str,
    collection_name: str,
    query: str,
    top_k: int = 3,
    where: dict[str, Any] | None = None,
) -> list[dict]:
    """Project-native equivalent of vector_store.as_retriever(search_kwargs={"k": top_k})."""
    collection = get_collection(chroma_path, collection_name)
    query_embedding = embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]
    distances = (
        results.get("distances", [[]])[0]
        if results.get("distances")
        else []
    )

    items = []
    for idx, doc_text in enumerate(docs):
        distance = distances[idx] if idx < len(distances) else 0.0
        items.append({
            "id": ids[idx],
            "document": doc_text,
            "metadata": metas[idx],
            "distance": distance,
            "score": _distance_to_score(distance),
            "rank": idx + 1,
        })

    return items


def retrieve_evidence(
    chroma_path: str,
    collection_name: str,
    period_start: str,
    period_end: str,
    section_queries: dict[str, str],
    top_k: int = 8,
) -> list[dict]:
    start_int = int(period_start.replace("-", ""))
    end_int = int(period_end.replace("-", ""))

    evidence = []
    evidence_no = 1

    for section, query in section_queries.items():
        results = retrieve_chunks(
            chroma_path=chroma_path,
            collection_name=collection_name,
            query=query,
            top_k=top_k,
            where={
                "$and": [
                    {"section": section},
                    {"publish_date_int": {"$gte": start_int}},
                    {"publish_date_int": {"$lte": end_int}},
                ]
            },
        )

        for chunk in results:
            meta = chunk["metadata"]
            evidence_item = EvidenceItem(
                evidence_id=f"E{evidence_no:02d}",
                section=SectionType(section),
                chunk_id=chunk["id"],
                doc_id=meta.get("doc_id", ""),
                title=meta.get("title", ""),
                source_url=meta.get("source_url", ""),
                source_name=meta.get("source_name", ""),
                source_type=meta.get("source_type", "unknown"),
                publish_date=meta.get("publish_date") or None,
                esg_dim=meta.get("esg_dim", "Unknown"),
                text=chunk["document"][:700],
                score=chunk["score"],
                rank=chunk["rank"],
                authority_score=float(meta.get("authority_score", 0.5) or 0.5),
                relevance_reason=f"Matched section={section}; query={query}",
            )

            evidence.append(evidence_item.model_dump(mode="json"))
            evidence_no += 1

    return evidence


def _distance_to_score(distance: Any) -> float:
    try:
        d = float(distance)
    except Exception:
        return 0.0

    score = 1.0 / (1.0 + max(d, 0.0))
    return round(score, 4)
