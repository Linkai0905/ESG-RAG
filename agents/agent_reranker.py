from __future__ import annotations

import json
from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from schemas import ScoreResult, AgentRerankDecision
from services.langsmith_utils import wrap_openai_client


PROMPT = """
你是信息检索重排Agent。

你只判断候选资料是否适合写入指定 section。
不要扩写事实，不要生成报告。

section_id:
{section_id}

section_query:
{section_query}

report_period:
{report_period}

请对 candidates 逐条打分：
- semantic_relevance: 1-5
- section_fit: 1-5
- evidence_strength: 1-5
- novelty: 1-5
- agent_score: 0-100
- reason: 简要原因

输出 JSON 数组。

candidates:
{candidates}
"""


def rerank_with_agent(
    section_id: str,
    section_query: str,
    report_period: dict,
    scored_candidates: list[dict],
    algorithm_weight: float = 0.8,
    agent_weight: float = 0.2,
) -> list[dict]:
    if not scored_candidates:
        return []

    payload = []

    for raw in scored_candidates:
        item = ScoreResult.model_validate(raw)
        c = item.candidate

        payload.append({
            "candidate_id": c.candidate_id,
            "title": c.title,
            "snippet": c.snippet,
            "publish_date": c.publish_date,
            "url": c.canonical_url,
            "origin": c.origin,
            "algorithm_score": item.algorithm_score,
            "score_breakdown": item.score_breakdown,
            "body_preview": c.body_text[:800],
        })

    prompt = PROMPT.format(
        section_id=section_id,
        section_query=section_query,
        report_period=json.dumps(report_period, ensure_ascii=False),
        candidates=json.dumps(payload, ensure_ascii=False, indent=2),
    )

    client_kwargs = {"api_key": LLM_API_KEY}
    if LLM_BASE_URL:
        client_kwargs["base_url"] = LLM_BASE_URL

    client = wrap_openai_client(OpenAI(**client_kwargs))

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    text = resp.choices[0].message.content or "[]"

    try:
        decisions_raw = json.loads(text)
    except Exception:
        start = text.find("[")
        end = text.rfind("]")
        decisions_raw = json.loads(text[start:end + 1])

    decisions = {}

    for d in decisions_raw:
        obj = AgentRerankDecision.model_validate(d)
        decisions[obj.candidate_id] = obj

    output = []

    for raw in scored_candidates:
        item = ScoreResult.model_validate(raw)
        decision = decisions.get(item.candidate.candidate_id)

        if decision:
            item.agent_score = decision.agent_score
            item.agent_reason = decision.reason
            item.final_score = round(
                item.algorithm_score * algorithm_weight
                + decision.agent_score * agent_weight,
                2,
            )
            item.selected_by = "rule_scorer_plus_agent"
        else:
            item.final_score = item.algorithm_score

        output.append(item.model_dump(mode="json"))

    output.sort(
        key=lambda x: (
            x["candidate"]["pinned"],
            x.get("final_score") or x["algorithm_score"],
        ),
        reverse=True,
    )

    return output
