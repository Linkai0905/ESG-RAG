# agents/report_generator.py
from __future__ import annotations

import json

from services.llm_client import chat_text


REPORT_PROMPT = """
你是上市公司ESG月报撰写助手。

请基于 evidence_pack 和 impact_assessments，
为【{company}】生成一份 ESG 月报草稿。

报告周期：
{period_start} 至 {period_end}

严格规则：
1. 只能使用 evidence_pack 和 impact_assessments 中的信息，不得编造。
2. 每个重要事实后必须标注证据编号，例如 [E03]。
3. 如果证据不足，请写“本月公开信息有限，建议持续关注”。
4. 内容必须包含：
   - ESG政策、评级、标准等相关动态
   - 客户所属行业层面的新闻动态、最佳实践
   - 客户公司动态对ESG的影响和建议
   - 对标企业ESG关键行动及启示
5. 建议必须具体到披露、数据跟踪、风险预警、管理优化、投资者沟通。
6. 输出 Markdown。

报告结构：

# {company} ESG月报草稿
报告周期：{period_start} 至 {period_end}

## 一、本月摘要

## 二、ESG政策、评级、标准动态

## 三、行业动态与最佳实践

## 四、{company}公司动态及ESG影响

## 五、对标企业ESG关键行动

## 六、下月建议关注事项

## 七、证据附录

evidence_pack:
{evidence_pack}

impact_assessments:
{impact_assessments}
"""


def generate_report(
    company: str,
    period_start: str,
    period_end: str,
    evidence_pack: list[dict],
    impact_assessments: list[dict],
) -> str:
    prompt = REPORT_PROMPT.format(
        company=company,
        period_start=period_start,
        period_end=period_end,
        evidence_pack=json.dumps(evidence_pack, ensure_ascii=False, indent=2),
        impact_assessments=json.dumps(impact_assessments, ensure_ascii=False, indent=2),
    )

    return chat_text(prompt, temperature=0.2)