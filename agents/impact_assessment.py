# agents/impact_assessment.py
from __future__ import annotations

import json

from schemas import ESGImpactAssessment
from services.llm_client import chat_json


IMPACT_PROMPT = """
Role: ESG impact assessment analyst.

Evidence boundary:
- Use only `evidence_pack`.
- Do not introduce external facts.
- Every assessment must reference at least one `evidence_id`.

Assessment rules:
1. Identify the event represented by each material evidence item.
2. Classify ESG dimension, impact direction, and materiality.
3. Provide risk, opportunity, recommendation, action owner, confidence, and caveat.
4. When evidence is insufficient, set `impact_direction` to `uncertain` and keep `confidence` <= 0.55.
5. For non-official sources, keep `confidence` <= 0.75.
6. Recommendations must map to disclosure, data tracking, risk monitoring, management improvement, or investor communication.

Return one JSON object with this schema:

{{
  "assessments": [
    {{
      "assessment_id": "A01",
      "related_evidence_ids": ["E01"],
      "subject": "事项主体",
      "subject_type": "policy / industry / company / peer",
      "event_summary": "事件摘要",
      "esg_dimension": "E / S / G / Mixed / Unknown",
      "impact_direction": "positive / negative / neutral / uncertain",
      "materiality": "high / medium / low / unknown",
      "risk": "风险判断",
      "opportunity": "机会判断",
      "recommendation": "建议动作",
      "action_owner": "ESG披露 / 环境管理 / 安全生产 / 投资者关系 / 合规治理 / 战略管理 / 数据管理 / 待确认",
      "confidence": 0.0,
      "caveat": "限制说明"
    }}
  ]
}}

evidence_pack:
{evidence_pack}
"""


def assess_impact(evidence_pack: list[dict]) -> list[dict]:
    prompt = IMPACT_PROMPT.format(
        evidence_pack=json.dumps(evidence_pack, ensure_ascii=False, indent=2)
    )

    raw = chat_json(
        prompt,
        temperature=0.1,
        system_prompt="Return a valid JSON object for ESG impact assessment. No Markdown.",
    )

    items = raw.get("assessments", [])

    assessments = []
    for item in items:
        obj = ESGImpactAssessment.model_validate(item)
        assessments.append(obj.model_dump(mode="json"))

    return assessments
