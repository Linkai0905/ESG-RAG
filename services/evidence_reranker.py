from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from config import RERANK_MAX_TEXT_CHARS, RERANK_MODEL
from services.llm_client import chat_json


RERANK_PROMPT = """
你是 RAG 证据重排器，只判断 evidence chunk 是否适合支撑 ESG 月报对应章节。
不要生成报告，不要扩写事实。

公司：{company}
报告周期：{period_start} 至 {period_end}
章节：{section}
章节检索目标：{section_query}

请对每条 evidence 打 0-10 分：
- 0：完全无关、明显对象错误、无法支撑该章节
- 1-2：只有 ESG/行业话题相似，但不能回答本章节问题
- 3-5：可作为背景，但不能直接支撑正文判断
- 6-8：能支撑章节中的一个具体判断
- 9-10：高度相关，能直接作为正文核心证据

重点区分：
- 同话题不等于能回答
- 同行业不等于同公司
- 同公司新闻不等于 ESG 相关
- 背景政策不等于公司动态证据

输出 JSON object，格式必须为：
{{
  "items": [
    {{
      "evidence_id": "E01",
      "score": 0,
      "usage": "body|background|drop",
      "reason": "一句话说明为什么"
    }}
  ]
}}

evidence:
{evidence_payload}
"""


def rerank_evidence_pack(
    evidence_pack: list[dict],
    *,
    company: str,
    period_start: str,
    period_end: str,
    section_queries: dict[str, str],
    rerank_sections: set[str],
    top_k: int,
    min_score: float,
    default_top_k: int,
) -> tuple[list[dict], list[dict]]:
    grouped = _group_by_section(evidence_pack)
    final_evidence: list[dict] = []
    decisions: list[dict] = []

    for section, items in grouped.items():
        if section not in rerank_sections:
            final_evidence.extend(items[:default_top_k])
            continue

        section_decisions = _rerank_section(
            items=items,
            company=company,
            period_start=period_start,
            period_end=period_end,
            section=section,
            section_query=section_queries.get(section, ""),
        )
        decisions.extend(section_decisions)

        decision_by_id = {
            x["evidence_id"]: x
            for x in section_decisions
        }

        scored_items = []
        for item in items:
            decision = decision_by_id.get(item.get("evidence_id", ""))
            if not decision:
                continue
            score = float(decision.get("score", 0) or 0)
            enriched = dict(item)
            enriched["score"] = round(score / 10, 4)
            enriched["relevance_reason"] = (
                f"Reranker {score:.1f}/10: {decision.get('reason', '')}"
            )
            scored_items.append((score, enriched))

        selected = [
            item
            for score, item in sorted(scored_items, key=lambda x: x[0], reverse=True)
            if score >= min_score
        ][:top_k]

        selected_ids = {x.get("evidence_id", "") for x in selected}
        for decision in section_decisions:
            decision["selected"] = decision.get("evidence_id", "") in selected_ids

        final_evidence.extend(selected)

    return final_evidence, decisions


def _group_by_section(evidence_pack: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    section_order: list[str] = []

    for item in evidence_pack:
        section = str(item.get("section", "unknown"))
        if section not in grouped:
            section_order.append(section)
        grouped[section].append(item)

    return {section: grouped[section] for section in section_order}


def _rerank_section(
    *,
    items: list[dict],
    company: str,
    period_start: str,
    period_end: str,
    section: str,
    section_query: str,
) -> list[dict]:
    payload = [_payload_item(item) for item in items]
    prompt = RERANK_PROMPT.format(
        company=company,
        period_start=period_start,
        period_end=period_end,
        section=section,
        section_query=section_query,
        evidence_payload=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    try:
        result = chat_json(
            prompt,
            temperature=0,
            model=RERANK_MODEL,
            system_prompt="你是严格的 RAG evidence reranker，只输出合法 JSON object。",
        )
        return _normalize_decisions(result, items)
    except Exception as e:
        return _fallback_decisions(items, error=e)


def _payload_item(item: dict) -> dict:
    return {
        "evidence_id": item.get("evidence_id", ""),
        "title": item.get("title", ""),
        "source_name": item.get("source_name", ""),
        "source_type": item.get("source_type", ""),
        "publish_date": item.get("publish_date", ""),
        "source_url": item.get("source_url", ""),
        "embedding_score": item.get("score", 0),
        "text": str(item.get("text", ""))[:RERANK_MAX_TEXT_CHARS],
    }


def _normalize_decisions(result: Any, items: list[dict]) -> list[dict]:
    raw_items = result.get("items", []) if isinstance(result, dict) else []
    known_ids = {item.get("evidence_id", "") for item in items}
    output = []

    for raw in raw_items:
        evidence_id = str(raw.get("evidence_id", ""))
        if evidence_id not in known_ids:
            continue
        score = _clip_score(raw.get("score", 0))
        output.append({
            "section": _section_for_id(items, evidence_id),
            "evidence_id": evidence_id,
            "score": score,
            "usage": _normalize_usage(raw.get("usage", ""), score),
            "reason": str(raw.get("reason", ""))[:300],
            "fallback": False,
        })

    decided = {x["evidence_id"] for x in output}
    missing = [
        item for item in items
        if item.get("evidence_id", "") not in decided
    ]
    output.extend(_fallback_decisions(missing))
    return output


def _fallback_decisions(items: list[dict], error: Exception | None = None) -> list[dict]:
    output = []
    for item in items:
        embedding_score = float(item.get("score", 0) or 0)
        score = _clip_score(round(embedding_score * 10, 2))
        output.append({
            "section": str(item.get("section", "unknown")),
            "evidence_id": item.get("evidence_id", ""),
            "score": score,
            "usage": _normalize_usage("", score),
            "reason": (
                "reranker 调用失败，使用 embedding 分数兜底"
                if error else
                "reranker 未返回该证据评分，使用 embedding 分数兜底"
            ),
            "fallback": True,
            "error": str(error)[:300] if error else "",
        })
    return output


def _clip_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        score = 0.0
    return max(0.0, min(10.0, score))


def _normalize_usage(value: str, score: float) -> str:
    value = str(value or "").lower()
    if value in {"body", "background", "drop"}:
        return value
    if score >= 6:
        return "body"
    if score >= 3:
        return "background"
    return "drop"


def _section_for_id(items: list[dict], evidence_id: str) -> str:
    for item in items:
        if item.get("evidence_id") == evidence_id:
            return str(item.get("section", "unknown"))
    return "unknown"
