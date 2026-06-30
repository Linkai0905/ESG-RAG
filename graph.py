# graph.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from config import make_collection_name
from langgraph.graph import StateGraph, START, END

from config import (
    DEFAULT_COMPANY,
    DEFAULT_ANCHOR_DATE,
    EVIDENCE_TOP_K_PER_SECTION,
    RERANK_ENABLED,
    RERANK_MIN_SCORE,
    RERANK_PRESELECT_K,
    RERANK_SECTIONS,
    RERANK_TOP_K,
    calc_period,
    make_run_id,
    build_run_dirs,
    SECTION_RETRIEVAL_QUERIES,
)

from schemas import (
    ESGWorkflowState,
    FetchResult,
    UrlCandidate,
    UrlQueueItem,
    ParsedDoc,
)

from agents.company_discovery import discover_company
from agents.search_agents import build_search_tasks, run_search_agent, run_section_search_agent
from agents.impact_assessment import assess_impact as llm_assess_impact
from agents.report_generator import generate_report as llm_generate_report

from services.url_normalizer import normalize_url
from services.merge_urls_node import merge_urls_node as merge_ranked_urls_node
from services.browser_worker import fetch_batch
from services.html_parser import parse_html_to_markdown
from services.mineru_parser import parse_pdf_with_mineru
from services.pdf_link_extractor import extract_pdf_candidates
from services.chunker import parsed_docs_to_chunks
from services.chroma_store import add_chunks, retrieve_evidence
from services.evidence_reranker import rerank_evidence_pack
from services.exporter import export_all, save_json


# =========================
# Helpers
# =========================

def _run_paths(state: ESGWorkflowState) -> dict:
    return build_run_dirs(state["run_id"])


def _merge_metrics(state: ESGWorkflowState, update: dict) -> dict:
    metrics = dict(state.get("metrics", {}))
    metrics.update(update)
    return metrics


def _merge_errors(state: ESGWorkflowState, stage: str, error: Exception) -> list[dict]:
    errors = list(state.get("errors", []))
    errors.append({
        "stage": stage,
        "error": str(error),
    })
    return errors


def _save_run_json(state: ESGWorkflowState, relative_path: str, data: Any) -> None:
    run_paths = _run_paths(state)
    path = run_paths["base"] / relative_path
    save_json(path, data)


def _take_top_k_by_section(items: list[dict], top_k: int) -> list[dict]:
    counts: dict[str, int] = {}
    output = []

    for item in items:
        section = item.get("section", "unknown")
        count = counts.get(section, 0)
        if count >= top_k:
            continue
        output.append(item)
        counts[section] = count + 1

    return output


def _find_search_task(state: ESGWorkflowState, section: str) -> dict | None:
    for task in state.get("search_tasks", []):
        if task.get("section") == section:
            return task
    return None


def _run_one_search_node(state: ESGWorkflowState, section: str) -> dict:
    task = _find_search_task(state, section)

    if not task:
        return {
            "url_candidates": [],
            "errors": [{
                "stage": f"search_{section}",
                "error": f"Search task not found for section={section}",
            }],
        }

    try:
        candidates = run_section_search_agent(
            section_id=section,
            report_period={
                "start": state["period_start"],
                "end": state["period_end"],
            },
            run_paths=_run_paths(state),
        )
        return {
            "url_candidates": candidates,
        }

    except Exception as e:
        return {
            "url_candidates": [],
            "errors": [{
                "stage": f"search_{section}",
                "error": str(e),
            }],
        }


# =========================
# Nodes
# =========================

def init_context(state: ESGWorkflowState) -> dict:
    company = state.get("company") or DEFAULT_COMPANY
    anchor_date = state.get("anchor_date") or DEFAULT_ANCHOR_DATE

    period_start, period_end = calc_period(anchor_date)
    run_id = make_run_id(company, anchor_date)
    run_paths = build_run_dirs(run_id)

    collection_name = make_collection_name(
        company=company,
        period_start=period_start,
        period_end=period_end,
    )

    return {
        "run_id": run_id,
        "company": company,
        "anchor_date": anchor_date,
        "period_start": period_start,
        "period_end": period_end,
        "run_paths": {k: str(v) for k, v in run_paths.items()},
        "chroma_path": str(run_paths["chroma"]),
        "collection_name": collection_name,
        "errors": [],
        "metrics": {
            "period_start": period_start,
            "period_end": period_end,
            "collection_name": collection_name,
        },
    }

def company_discovery_node(state: ESGWorkflowState) -> dict:
    profile = discover_company(state["company"])

    _save_run_json(
        state,
        "queue/company_profile.json",
        profile,
    )

    return {
        "company_profile": profile,
        "metrics": _merge_metrics(state, {
            "company": state["company"],
            "peer_count": len(profile.get("peer_companies", [])),
        }),
    }


def build_search_tasks_node(state: ESGWorkflowState) -> dict:
    tasks = build_search_tasks(
        period_start=state["period_start"],
        period_end=state["period_end"],
    )

    _save_run_json(
        state,
        "queue/search_tasks.json",
        tasks,
    )

    return {
        "search_tasks": tasks,
        "metrics": _merge_metrics(state, {
            "search_task_count": len(tasks),
        }),
    }


def run_search_agents_node(state: ESGWorkflowState) -> dict:
    """
    Legacy sequential search node retained for compatibility.
    The active graph uses section-level parallel search nodes.
    """
    all_candidates: list[dict] = []

    for task in state.get("search_tasks", []):
        try:
            candidates = run_search_agent(task)
            all_candidates.extend(candidates)
        except Exception as e:
            return {
                "url_candidates": all_candidates,
                "errors": _merge_errors(state, "run_search_agents", e),
            }

    _save_run_json(
        state,
        "queue/url_candidates.json",
        all_candidates,
    )

    return {
        "url_candidates": all_candidates,
        "metrics": _merge_metrics(state, {
            "url_candidate_count": len(all_candidates),
        }),
    }


def search_policy_node(state: ESGWorkflowState) -> dict:
    return _run_one_search_node(state, "policy")


def search_industry_node(state: ESGWorkflowState) -> dict:
    return _run_one_search_node(state, "industry")


def search_company_node(state: ESGWorkflowState) -> dict:
    return _run_one_search_node(state, "company")


def search_peer_node(state: ESGWorkflowState) -> dict:
    return _run_one_search_node(state, "peer")


def merge_urls_node(state: ESGWorkflowState) -> dict:
    return merge_ranked_urls_node(state)


def fetch_pages_node(state: ESGWorkflowState) -> dict:
    run_paths = _run_paths(state)
    url_queue = state.get("url_queue", [])

    fetched_docs = fetch_batch(
        url_queue=url_queue,
        run_paths=run_paths,
    )

    _save_run_json(
        state,
        "queue/fetched_docs.json",
        fetched_docs,
    )

    success_count = sum(1 for x in fetched_docs if x.get("status") == "success")
    failed_count = sum(1 for x in fetched_docs if x.get("status") == "failed")

    return {
        "fetched_docs": fetched_docs,
        "metrics": _merge_metrics(state, {
            "fetch_success_count": success_count,
            "fetch_failed_count": failed_count,
        }),
    }


def _pdf_candidates_to_queue(
    pdf_candidates: list[dict],
    parent_url: str,
    parent_url_id: str,
) -> list[dict]:
    queue: dict[str, UrlQueueItem] = {}

    for raw in pdf_candidates:
        candidate = UrlCandidate.model_validate(raw)
        canonical_url = normalize_url(candidate.url)

        item = UrlQueueItem.from_candidate(
            candidate=candidate,
            canonical_url=canonical_url,
            parent_url=parent_url,
            inherited_from_url_id=parent_url_id,
        )

        old = queue.get(item.url_id)
        if old is None or item.priority > old.priority:
            queue[item.url_id] = item

    return [x.model_dump(mode="json") for x in queue.values()]


def parse_documents_node(state: ESGWorkflowState) -> dict:
    """
    Parser Router:
    - PDF -> MinerU
    - HTML -> main text extraction
    - PDF links discovered in HTML -> bounded attachment fetch and parse
    """
    run_paths = _run_paths(state)

    parsed_docs: list[dict] = []
    discovered_pdf_candidates: list[dict] = []
    pdf_queue_all: list[dict] = []

    for raw in state.get("fetched_docs", []):
        try:
            fetched = FetchResult.model_validate(raw)

            if fetched.status != "success":
                continue

            if fetched.is_pdf:
                parsed = parse_pdf_with_mineru(fetched, run_paths)
                parsed_docs.append(parsed.model_dump(mode="json"))
                continue

            if fetched.is_html:
                parsed = parse_html_to_markdown(fetched, run_paths)
                parsed_docs.append(parsed.model_dump(mode="json"))

                pdf_candidates = extract_pdf_candidates(fetched)
                discovered_pdf_candidates.extend(pdf_candidates)

                if pdf_candidates:
                    parent_url = fetched.final_url or fetched.canonical_url
                    pdf_queue = _pdf_candidates_to_queue(
                        pdf_candidates=pdf_candidates,
                        parent_url=parent_url,
                        parent_url_id=fetched.url_id,
                    )
                    pdf_queue_all.extend(pdf_queue)

        except Exception as e:
            return {
                "parsed_docs": parsed_docs,
                "errors": _merge_errors(state, "parse_documents", e),
            }

    # Keep attachment expansion bounded so one noisy source cannot dominate the run.
    pdf_queue_all = pdf_queue_all[:10]

    if pdf_queue_all:
        pdf_fetched = fetch_batch(
            url_queue=pdf_queue_all,
            run_paths=run_paths,
        )

        for raw in pdf_fetched:
            try:
                fetched = FetchResult.model_validate(raw)
                if fetched.status == "success" and fetched.is_pdf:
                    parsed = parse_pdf_with_mineru(fetched, run_paths)
                    parsed_docs.append(parsed.model_dump(mode="json"))
            except Exception as e:
                # Attachment parsing failures are recorded but do not block primary sources.
                state_errors = _merge_errors(state, "parse_pdf_attachment", e)

        _save_run_json(
            state,
            "queue/pdf_attachment_queue.json",
            pdf_queue_all,
        )

    _save_run_json(
        state,
        "queue/discovered_pdf_candidates.json",
        discovered_pdf_candidates,
    )
    _save_run_json(
        state,
        "queue/parsed_docs.json",
        parsed_docs,
    )

    parsed_success_count = sum(
        1 for x in parsed_docs
        if x.get("status") == "success" and x.get("markdown_path")
    )

    return {
        "parsed_docs": parsed_docs,
        "discovered_pdf_urls": discovered_pdf_candidates,
        "metrics": _merge_metrics(state, {
            "parsed_doc_count": len(parsed_docs),
            "parsed_success_count": parsed_success_count,
            "discovered_pdf_count": len(discovered_pdf_candidates),
        }),
    }


def index_chroma_node(state: ESGWorkflowState) -> dict:
    chunks = parsed_docs_to_chunks(
        parsed_docs=state.get("parsed_docs", []),
        run_id=state["run_id"],
        company=state["company"],
    )

    add_chunks(
        chroma_path=state["chroma_path"],
        collection_name=state["collection_name"],
        chunks=chunks,
    )

    _save_run_json(
        state,
        "queue/chunks_preview.json",
        chunks[:20],
    )

    return {
        "chunks": chunks,
        "metrics": _merge_metrics(state, {
            "chunk_count": len(chunks),
        }),
    }


def retrieve_evidence_node(state: ESGWorkflowState) -> dict:
    retrieve_top_k = (
        max(RERANK_PRESELECT_K, EVIDENCE_TOP_K_PER_SECTION)
        if RERANK_ENABLED
        else EVIDENCE_TOP_K_PER_SECTION
    )
    raw_evidence_pack = retrieve_evidence(
        chroma_path=state["chroma_path"],
        collection_name=state["collection_name"],
        period_start=state["period_start"],
        period_end=state["period_end"],
        section_queries=SECTION_RETRIEVAL_QUERIES,
        top_k=retrieve_top_k,
    )

    evidence_pack = raw_evidence_pack
    rerank_decisions = []
    rerank_fallback = False

    if RERANK_ENABLED:
        _save_run_json(
            state,
            "reports/evidence_raw.json",
            raw_evidence_pack,
        )

        try:
            evidence_pack, rerank_decisions = rerank_evidence_pack(
                raw_evidence_pack,
                company=state["company"],
                period_start=state["period_start"],
                period_end=state["period_end"],
                section_queries=SECTION_RETRIEVAL_QUERIES,
                rerank_sections=set(RERANK_SECTIONS),
                top_k=RERANK_TOP_K,
                min_score=RERANK_MIN_SCORE,
                default_top_k=EVIDENCE_TOP_K_PER_SECTION,
            )
        except Exception as e:
            rerank_fallback = True
            evidence_pack = _take_top_k_by_section(
                raw_evidence_pack,
                EVIDENCE_TOP_K_PER_SECTION,
            )
            rerank_decisions = [{
                "fallback": True,
                "error": str(e),
                "reason": "evidence reranker failed; raw embedding evidence used",
            }]

        _save_run_json(
            state,
            "reports/evidence_rerank_decisions.json",
            rerank_decisions,
        )

    _save_run_json(
        state,
        "reports/evidence.json",
        evidence_pack,
    )

    section_counts = {}
    for item in evidence_pack:
        section = item.get("section", "unknown")
        section_counts[section] = section_counts.get(section, 0) + 1

    raw_section_counts = {}
    for item in raw_evidence_pack:
        section = item.get("section", "unknown")
        raw_section_counts[section] = raw_section_counts.get(section, 0) + 1

    rerank_selected_counts = {}
    for item in evidence_pack:
        section = item.get("section", "unknown")
        if section in set(RERANK_SECTIONS):
            rerank_selected_counts[section] = rerank_selected_counts.get(section, 0) + 1

    return {
        "evidence_pack": evidence_pack,
        "metrics": _merge_metrics(state, {
            "evidence_count": len(evidence_pack),
            "evidence_section_counts": section_counts,
            "evidence_raw_count": len(raw_evidence_pack),
            "evidence_raw_section_counts": raw_section_counts,
            "evidence_rerank_enabled": RERANK_ENABLED,
            "evidence_rerank_sections": list(RERANK_SECTIONS),
            "evidence_rerank_selected_counts": rerank_selected_counts,
            "evidence_rerank_fallback": rerank_fallback,
        }),
    }


def _fallback_assessments(evidence_pack: list[dict]) -> list[dict]:
    """
    Deterministic fallback used when assessment generation is unavailable.
    """
    assessments = []

    for idx, ev in enumerate(evidence_pack[:12], start=1):
        assessments.append({
            "assessment_id": f"A{idx:02d}",
            "related_evidence_ids": [ev.get("evidence_id", "")],
            "subject": ev.get("title", "") or ev.get("section", ""),
            "subject_type": ev.get("section", "company"),
            "event_summary": ev.get("text", "")[:160],
            "esg_dimension": ev.get("esg_dim", "Mixed"),
            "impact_direction": "uncertain",
            "materiality": "medium",
            "risk": "该事项可能影响ESG披露、合规管理或投资者沟通，需结合正式公告进一步确认。",
            "opportunity": "可纳入月度议题跟踪，用于后续披露准备、风险识别和管理优化。",
            "recommendation": "纳入ESG月度监测清单，补充官方来源核验，并视重要性形成披露或内部管理动作。",
            "action_owner": "ESG披露",
            "confidence": 0.5,
            "caveat": "评估生成不可用时的规则化结果，需复核后使用。",
        })

    return assessments


def assess_impact_node(state: ESGWorkflowState) -> dict:
    evidence_pack = state.get("evidence_pack", [])

    try:
        impact_assessments = llm_assess_impact(evidence_pack)
    except Exception as e:
        impact_assessments = _fallback_assessments(evidence_pack)
        errors = _merge_errors(state, "assess_impact", e)
        return {
            "impact_assessments": impact_assessments,
            "errors": errors,
            "metrics": _merge_metrics(state, {
                "impact_assessment_count": len(impact_assessments),
                "impact_assessment_fallback": True,
            }),
        }

    _save_run_json(
        state,
        "reports/impact_assessments.json",
        impact_assessments,
    )

    return {
        "impact_assessments": impact_assessments,
        "metrics": _merge_metrics(state, {
            "impact_assessment_count": len(impact_assessments),
            "impact_assessment_fallback": False,
        }),
    }


def _fallback_report(state: ESGWorkflowState) -> str:
    evidence_pack = state.get("evidence_pack", [])
    impact_assessments = state.get("impact_assessments", [])

    lines = [
        f"# {state['company']} ESG月报",
        "",
        f"报告周期：{state['period_start']} 至 {state['period_end']}",
        "",
        "> 注：本报告基于公开资料和结构化证据生成，正式使用前需完成业务与合规复核。",
        "",
        "## 一、本月摘要",
        "",
        "- 本月系统已完成政策、行业、公司、对标企业四类公开资料的检索和证据整理。",
        "- 报告写作服务不可用，以下内容由规则模板生成。",
        "",
        "## 二、ESG政策、评级、标准动态",
        "",
    ]

    for ev in evidence_pack:
        if ev.get("section") == "policy":
            lines.append(
                f"- {ev.get('title', '未命名资料')} [{ev.get('evidence_id')}]"
            )

    lines.extend([
        "",
        "## 三、行业动态与最佳实践",
        "",
    ])

    for ev in evidence_pack:
        if ev.get("section") == "industry":
            lines.append(
                f"- {ev.get('title', '未命名资料')} [{ev.get('evidence_id')}]"
            )

    lines.extend([
        "",
        f"## 四、{state['company']}公司动态及ESG影响",
        "",
    ])

    for ev in evidence_pack:
        if ev.get("section") == "company":
            lines.append(
                f"- {ev.get('title', '未命名资料')} [{ev.get('evidence_id')}]"
            )

    lines.extend([
        "",
        "## 五、对标企业ESG关键行动",
        "",
    ])

    for ev in evidence_pack:
        if ev.get("section") == "peer":
            lines.append(
                f"- {ev.get('title', '未命名资料')} [{ev.get('evidence_id')}]"
            )

    lines.extend([
        "",
        "## 六、下月建议关注事项",
        "",
    ])

    for item in impact_assessments[:8]:
        ids = ",".join(item.get("related_evidence_ids", []))
        lines.append(
            f"- {item.get('recommendation', '')} [{ids}]"
        )

    lines.extend([
        "",
        "## 七、证据附录",
        "",
        "| 编号 | 标题 | 来源 | 日期 | URL |",
        "|---|---|---|---|---|",
    ])

    for ev in evidence_pack:
        lines.append(
            f"| {ev.get('evidence_id', '')} | "
            f"{ev.get('title', '')} | "
            f"{ev.get('source_name', '')} | "
            f"{ev.get('publish_date', '')} | "
            f"{ev.get('source_url', '')} |"
        )

    return "\n".join(lines)


def generate_report_node(state: ESGWorkflowState) -> dict:
    try:
        report_markdown = llm_generate_report(
            company=state["company"],
            period_start=state["period_start"],
            period_end=state["period_end"],
            evidence_pack=state.get("evidence_pack", []),
            impact_assessments=state.get("impact_assessments", []),
            parsed_docs=state.get("parsed_docs", []),
        )
    except Exception as e:
        report_markdown = _fallback_report(state)
        return {
            "report_markdown": report_markdown,
            "errors": _merge_errors(state, "generate_report", e),
            "metrics": _merge_metrics(state, {
                "report_fallback": True,
                "report_length": len(report_markdown),
            }),
        }

    return {
        "report_markdown": report_markdown,
        "metrics": _merge_metrics(state, {
            "report_fallback": False,
            "report_length": len(report_markdown),
        }),
    }


def export_files_node(state: ESGWorkflowState) -> dict:
    run_paths = _run_paths(state)

    output_paths = export_all(
        run_paths=run_paths,
        report_markdown=state.get("report_markdown", ""),
        evidence_pack=state.get("evidence_pack", []),
        impact_assessments=state.get("impact_assessments", []),
    )

    # Persist final diagnostics after report export.
    save_json(
        run_paths["reports"] / "metrics.json",
        state.get("metrics", {}),
    )
    save_json(
        run_paths["reports"] / "errors.json",
        state.get("errors", []),
    )

    return {
        "output_paths": output_paths,
        "metrics": _merge_metrics(state, {
            "export_done": True,
        }),
    }


# =========================
# Build Graph
# =========================

def build_graph():
    builder = StateGraph(ESGWorkflowState)

    builder.add_node("init_context", init_context)
    builder.add_node("company_discovery", company_discovery_node)
    builder.add_node("build_search_tasks", build_search_tasks_node)

    builder.add_node("search_policy", search_policy_node)
    builder.add_node("search_industry", search_industry_node)
    builder.add_node("search_company", search_company_node)
    builder.add_node("search_peer", search_peer_node)

    builder.add_node("merge_urls", merge_urls_node)
    builder.add_node("fetch_pages", fetch_pages_node)
    builder.add_node("parse_documents", parse_documents_node)
    builder.add_node("index_chroma", index_chroma_node)
    builder.add_node("retrieve_evidence", retrieve_evidence_node)
    builder.add_node("assess_impact", assess_impact_node)
    builder.add_node("generate_report", generate_report_node)
    builder.add_node("export_files", export_files_node)

    builder.add_edge(START, "init_context")
    builder.add_edge("init_context", "company_discovery")
    builder.add_edge("company_discovery", "build_search_tasks")

    # Section-level search fan-out.
    builder.add_edge("build_search_tasks", "search_policy")
    builder.add_edge("build_search_tasks", "search_industry")
    builder.add_edge("build_search_tasks", "search_company")
    builder.add_edge("build_search_tasks", "search_peer")

    # Merge only after all section searches have returned.
    builder.add_edge(
        ["search_policy", "search_industry", "search_company", "search_peer"],
        "merge_urls",
    )

    builder.add_edge("merge_urls", "fetch_pages")
    builder.add_edge("fetch_pages", "parse_documents")
    builder.add_edge("parse_documents", "index_chroma")
    builder.add_edge("index_chroma", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "assess_impact")
    builder.add_edge("assess_impact", "generate_report")
    builder.add_edge("generate_report", "export_files")
    builder.add_edge("export_files", END)

    return builder.compile()


# LangGraph Studio entrypoint.
# `langgraph.json` points to this compiled graph.
studio_graph = build_graph()
