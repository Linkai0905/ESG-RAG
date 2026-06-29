# services/chunker.py
from __future__ import annotations

from pathlib import Path

from schemas import (
    ParsedDoc,
    ChunkItem,
    ChunkMetadata,
    ESGDimension,
)


def split_text(text: str, max_chars: int = 180, overlap: int = 40) -> list[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = start + max_chars
        chunk = text[start:end].strip()

        if len(chunk) >= 80:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def classify_esg_dim(text: str) -> ESGDimension:
    if any(k in text for k in ["碳", "排放", "环保", "生态", "绿色", "能源", "水资源", "CCUS"]):
        return ESGDimension.E
    if any(k in text for k in ["安全生产", "员工", "职业健康", "社区", "供应链"]):
        return ESGDimension.S
    if any(k in text for k in ["治理", "披露", "董事会", "合规", "风险", "内控"]):
        return ESGDimension.G
    return ESGDimension.MIXED


def authority_score(source_type: str) -> float:
    if source_type in ["policy", "standard", "announcement", "official"]:
        return 0.95
    if source_type in ["rating", "best_practice"]:
        return 0.85
    if source_type in ["industry_news", "company_news", "peer_action"]:
        return 0.7
    return 0.5


def parsed_docs_to_chunks(
    parsed_docs: list[dict],
    run_id: str,
    company: str,
) -> list[dict]:
    all_chunks = []

    for raw in parsed_docs:
        doc = ParsedDoc.model_validate(raw)

        if not doc.markdown_path:
            continue

        path = Path(doc.markdown_path)
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        pieces = split_text(text)

        for idx, piece in enumerate(pieces):
            metadata = ChunkMetadata(
                run_id=run_id,
                section=doc.section,
                source_type=doc.source_type,
                source_url=doc.source_url,
                parent_url=doc.parent_url,
                title=doc.title,
                source_name=doc.source_name,
                publish_date=doc.publish_date,
                company=company if company in piece or company in doc.title else "",
                esg_dim=classify_esg_dim(piece),
                parser=doc.parser,
                doc_id=doc.doc_id,
                chunk_index=idx,
                authority_score=authority_score(doc.source_type),
                tags="",
            )

            chunk = ChunkItem.create(
                doc_id=doc.doc_id,
                text=piece,
                metadata=metadata,
            )

            all_chunks.append(chunk.model_dump(mode="json"))

    return all_chunks
