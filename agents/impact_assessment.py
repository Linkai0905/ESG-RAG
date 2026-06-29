# agents/impact_assessment.py
from __future__ import annotations

import json

from schemas import ESGImpactAssessment
from services.llm_client import chat_json


IMPACT_PROMPT = """
你是ESG影响评估Agent。
你只能基于 evidence_pack 中的证据进行判断，不能使用外部知识或编造事实。

任务：
1. 识别每条证据对应的事件。
2. 判断该事件对中国神华的 ESG 影响。
3. 输出风险、机会和建议。
4. 所有判断必须绑定 evidence_id。
5. 如果证据不足，impact_direction 写 uncertain，confidence 不得超过 0.55。
6. 如果来源不是官方、监管、交易所、公司公告，confidence 不得超过 0.75。
7. 建议必须是可执行动作，围绕披露、数据跟踪、风险预警、管理优化、投资者沟通展开。

必须输出一个 JSON object，格式如下：

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
        system_prompt="你是严格的ESG影响评估JSON生成器，只输出合法JSON object。",
    )

    items = raw.get("assessments", [])

    assessments = []
    for item in items:
        obj = ESGImpactAssessment.model_validate(item)
        assessments.append(obj.model_dump(mode="json"))

    return assessments
