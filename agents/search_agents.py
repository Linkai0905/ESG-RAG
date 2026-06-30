# agents/search_agents.py
from __future__ import annotations

from config import (
    build_search_queries,
    MANUAL_SOURCES_PATH,
    MIN_ONLINE_URLS_PER_SECTION,
    PRESELECT_K,
    SECTION_QUERIES,
    TOP_K_PER_SECTION,
    USE_AGENT_RERANK,
)
from schemas import UrlCandidate, SearchTask, SectionType, SourceType
from services.search_api import search_web
from services.section_candidate_retriever import retrieve_candidates_for_section


def _section_value(section) -> str:
    return section.value if hasattr(section, "value") else str(section)


def build_search_tasks(period_start: str, period_end: str) -> list[dict]:
    query_map = build_search_queries()
    tasks = []

    for section, queries in query_map.items():
        task = SearchTask(
            task_id=f"search_{section}",
            section=SectionType(section),
            queries=queries,
            period_start=period_start,
            period_end=period_end,
            top_k_per_query=5,
        )
        tasks.append(task.model_dump(mode="json"))

    return tasks


def run_section_search_agent(
    section_id: str,
    report_period: dict,
    run_paths: dict,
) -> list[dict]:
    queries = SECTION_QUERIES[section_id]

    return retrieve_candidates_for_section(
        section_id=section_id,
        section_queries=queries,
        report_period=report_period,
        manual_sources_path=MANUAL_SOURCES_PATH,
        run_paths=run_paths,
        top_k=TOP_K_PER_SECTION,
        preselect_k=PRESELECT_K,
        min_online_k=MIN_ONLINE_URLS_PER_SECTION,
        use_agent_rerank=USE_AGENT_RERANK,
    )


def run_search_agent(task: dict) -> list[dict]:
    task_obj = SearchTask.model_validate(task)
    section = _section_value(task_obj.section)

    candidates = []

    for query in task_obj.queries:
        results = search_web(
            query=query,
            start_date=task_obj.period_start,
            end_date=task_obj.period_end,
            top_k=task_obj.top_k_per_query,
            section=section,
        )

        for raw in results:
            if not raw.get("url"):
                continue

            candidate = UrlCandidate(
                url=raw["url"],
                title=raw.get("title", ""),
                snippet=raw.get("snippet", ""),
                source_name=raw.get("source_name", ""),
                publish_date=raw.get("publish_date"),
                section=SectionType(section),
                source_type=_infer_source_type(section, raw),
                query=query,
                discovered_by=f"{section}_search_agent",
                confidence=0.7,
                requires_browser=True,
                requires_mineru=raw["url"].lower().endswith(".pdf"),
                priority=_default_priority(section),
                reason=f"Search task {section} matched query: {query}",
            )
            candidates.append(candidate.model_dump(mode="json"))

    return candidates


def _infer_source_type(section: str, raw: dict) -> SourceType:
    url = raw.get("url", "").lower()
    title = raw.get("title", "")

    if section == "policy":
        if "评级" in title:
            return SourceType.RATING
        if "标准" in title or "准则" in title or "指引" in title:
            return SourceType.STANDARD
        return SourceType.POLICY

    if section == "industry":
        if "最佳实践" in title or "案例" in title:
            return SourceType.BEST_PRACTICE
        return SourceType.INDUSTRY_NEWS

    if section == "company":
        if "公告" in title or "sse" in url or "hkex" in url:
            return SourceType.ANNOUNCEMENT
        return SourceType.COMPANY_NEWS

    if section == "peer":
        return SourceType.PEER_ACTION

    return SourceType.UNKNOWN


def _default_priority(section: str) -> int:
    if section == "policy":
        return 90
    if section == "company":
        return 85
    if section == "peer":
        return 75
    return 70
