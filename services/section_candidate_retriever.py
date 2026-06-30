from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT, SEARCH_PROVIDER
from schemas import (
    CandidateOrigin,
    CrawledContent,
    EnrichedCandidate,
    ManualSourceItem,
    RankedUrlCandidate,
    ScoreResult,
    SourceType,
    sha256_text,
)
from services.light_crawler import LightCrawler
from services.search_api import search_web
from services.url_normalizer import normalize_url


def retrieve_candidates_for_section(
    section_id: str,
    section_queries: list[str],
    report_period: dict,
    manual_sources_path: str | Path,
    run_paths: dict,
    top_k: int = 8,
    preselect_k: int = 20,
    min_online_k: int = 0,
    use_agent_rerank: bool = False,
) -> list[dict]:
    section_query = " ".join(section_queries)
    crawler = LightCrawler(cache_dir=Path(run_paths["meta"]) / "manual_crawl")

    enriched: list[dict] = []
    enriched.extend(
        _load_manual_enriched_candidates(
            section_id=section_id,
            manual_sources_path=manual_sources_path,
            crawler=crawler,
        )
    )
    if SEARCH_PROVIDER != "manual":
        enriched.extend(
            _load_search_enriched_candidates(
                section_id=section_id,
                section_queries=section_queries,
                report_period=report_period,
                crawler=crawler,
                top_k=max(1, min(preselect_k, 10)),
            )
        )

    duplicate_urls = _duplicate_canonical_urls(enriched)
    duplicate_hashes = _duplicate_content_hashes(enriched)

    scored = []
    for item in enriched:
        canonical_url = item.get("canonical_url", "")
        content_hash = item.get("content_hash", "")
        scored.append(
            _score_candidate(
                item=item,
                query=section_query,
                section_id=section_id,
                report_period=report_period,
                duplicate_url=canonical_url in duplicate_urls,
                duplicate_content=bool(content_hash and content_hash in duplicate_hashes),
            )
        )

    scored.sort(
        key=lambda x: (
            x["candidate"]["pinned"],
            x.get("final_score") or x["algorithm_score"],
        ),
        reverse=True,
    )

    selected = scored[:preselect_k]

    if use_agent_rerank and selected:
        from agents.agent_reranker import rerank_with_agent

        selected = rerank_with_agent(
            section_id=section_id,
            section_query=section_query,
            report_period=report_period,
            scored_candidates=selected,
        )

    selected = _select_with_online_quota(
        scored_candidates=selected,
        top_k=top_k,
        min_online_k=min_online_k,
    )

    ranked_candidates = []
    for raw in selected:
        item = ScoreResult.model_validate(raw)
        c = item.candidate

        final_score = item.final_score or item.algorithm_score
        canonical_url = c.canonical_url

        ranked = RankedUrlCandidate(
            candidate_id=c.candidate_id,
            url_id=sha256_text(canonical_url)[:16],
            url=c.url,
            canonical_url=canonical_url,
            title=c.title,
            snippet=c.snippet,
            section=section_id,
            section_hint=c.section_hint,
            publish_date=c.publish_date,
            source_name=c.source_name,
            source_type=c.source_type,
            origin=c.origin,
            query=c.query,
            discovered_by=c.discovered_by,
            pinned=c.pinned,
            priority=c.priority,
            algorithm_score=item.algorithm_score,
            agent_score=item.agent_score,
            final_score=final_score,
            score_breakdown=item.score_breakdown,
            agent_reason=item.agent_reason,
            tags=",".join(c.tags),
            crawl_failed=c.crawl_failed,
            duplicate_url=c.duplicate_url,
            duplicate_content=c.duplicate_content,
            content_type=c.content_type,
            file_ext=c.file_ext,
        )

        ranked_candidates.append(ranked.model_dump(mode="json"))

    _save_section_debug(run_paths, section_id, "scored_candidates", selected)
    _save_section_debug(run_paths, section_id, "ranked_url_candidates", ranked_candidates)

    return ranked_candidates


def _load_manual_enriched_candidates(
    section_id: str,
    manual_sources_path: str | Path,
    crawler: LightCrawler,
) -> list[dict]:
    items = _load_manual_sources(manual_sources_path)
    enriched = []

    for item in items:
        if item.section_hint and item.section_hint != section_id:
            continue

        crawled = crawler.crawl(item.url)
        enriched.append(
            _manual_item_to_enriched(
                item=item,
                crawled=crawled,
                section_id=section_id,
            )
        )

    return enriched


def _load_search_enriched_candidates(
    section_id: str,
    section_queries: list[str],
    report_period: dict,
    crawler: LightCrawler,
    top_k: int,
) -> list[dict]:
    enriched = []

    for query in section_queries:
        results = search_web(
            query=query,
            start_date=report_period["start"],
            end_date=report_period["end"],
            top_k=top_k,
            section=section_id,
        )

        for raw in results:
            url = (raw.get("url") or "").strip()
            if not url:
                continue

            crawled = crawler.crawl(url)
            page = CrawledContent.model_validate(crawled)
            title = page.title or raw.get("title", "")
            snippet = page.snippet or raw.get("snippet", "")

            candidate = EnrichedCandidate(
                candidate_id=sha256_text(page.canonical_url),
                url=url,
                canonical_url=page.canonical_url,
                section_hint=section_id,
                priority=0,
                pinned=False,
                title=title,
                snippet=snippet,
                body_text=page.body_text,
                publish_date=raw.get("publish_date") or page.publish_date,
                source_name=raw.get("source_name") or page.source_name,
                source_type=_simple_source_type(raw.get("source_type", "")),
                origin=CandidateOrigin.WEB_SEARCH,
                query=query,
                discovered_by=f"{section_id}_search_agent",
                content_type=page.content_type,
                file_ext=page.file_ext,
                content_hash=page.content_hash,
                tags=[],
                crawl_failed=page.crawl_failed,
                error=page.error,
            )
            enriched.append(candidate.model_dump(mode="json"))

    return enriched


def _load_manual_sources(path: str | Path) -> list[ManualSourceItem]:
    path = _resolve_manual_path(path)
    if not path.exists():
        return []

    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

    items = []
    for row in rows:
        url = (row.get("url") or "").strip()
        local_path = (row.get("local_path") or "").strip()
        if local_path:
            file_path = Path(local_path).expanduser()
            if not file_path.is_absolute():
                file_path = PROJECT_ROOT / file_path
            url = file_path.as_uri()

        item = ManualSourceItem(
            url=url,
            title=(row.get("title") or _title_from_tags_or_note(row)).strip(),
            snippet=(row.get("snippet") or row.get("note") or "").strip(),
            section_hint=(row.get("section_hint") or row.get("section") or "").strip(),
            source_type_hint=(row.get("source_type_hint") or row.get("source_type") or "").strip(),
            priority=int(row.get("priority") or 3),
            pinned=_parse_bool(row.get("pinned")),
            expected_date=row.get("expected_date") or row.get("publish_date") or None,
            source_name_hint=(row.get("source_name_hint") or row.get("source_name") or "").strip(),
            tags=row.get("tags") or row.get("title") or "",
            note=row.get("note") or row.get("snippet") or "",
            query=row.get("query") or "",
            discovered_by=row.get("discovered_by") or "manual",
        )
        items.append(item)

    return items


def _manual_item_to_enriched(
    item: ManualSourceItem,
    crawled: dict,
    section_id: str,
) -> dict:
    page = CrawledContent.model_validate(crawled)
    title = page.title or item.title
    snippet = page.snippet or item.snippet or item.note
    source_name = item.source_name_hint or page.source_name
    source_type = _simple_source_type(item.source_type_hint)

    candidate = EnrichedCandidate(
        candidate_id=sha256_text(page.canonical_url),
        url=item.url,
        canonical_url=page.canonical_url,
        title=title,
        snippet=snippet,
        body_text=page.body_text,
        publish_date=item.expected_date or page.publish_date,
        source_name=source_name,
        source_type=source_type,
        section_hint=item.section_hint or section_id,
        priority=item.priority,
        pinned=item.pinned,
        origin=CandidateOrigin.MANUAL,
        query=item.query,
        discovered_by=item.discovered_by,
        content_type=page.content_type,
        file_ext=page.file_ext,
        content_hash=page.content_hash,
        tags=item.tags,
        crawl_failed=page.crawl_failed,
        error=page.error,
    )
    return candidate.model_dump(mode="json")


def _score_candidate(
    item: dict,
    query: str,
    section_id: str,
    report_period: dict,
    duplicate_url: bool = False,
    duplicate_content: bool = False,
) -> dict:
    candidate = EnrichedCandidate.model_validate(item)
    candidate.duplicate_url = duplicate_url
    candidate.duplicate_content = duplicate_content

    title_match = _keyword_coverage(query, candidate.title)
    snippet_match = _keyword_coverage(query, candidate.snippet)
    body_match = _keyword_coverage(query, candidate.body_text[:4000])

    score_breakdown = {
        "title_match": round(title_match * 30, 2),
        "snippet_match": round(snippet_match * 15, 2),
        "body_match": round(body_match * 8, 2),
        "date_bonus": _date_score(
            publish_date=candidate.publish_date,
            start=report_period["start"],
            end=report_period["end"],
        ),
        "section_hint_bonus": _section_hint_score(candidate.section_hint, section_id),
        "manual_boost": 15 if candidate.origin == CandidateOrigin.MANUAL.value else 0,
        "web_search_base": 5 if candidate.origin != CandidateOrigin.MANUAL.value else 0,
        "manual_priority": min(max(candidate.priority, 0), 5) * 5,
        "pinned_bonus": 20 if candidate.pinned else 0,
        "crawl_failed_penalty": -50 if candidate.crawl_failed else 0,
        "duplicate_url_penalty": -30 if duplicate_url else 0,
        "duplicate_content_penalty": -20 if duplicate_content else 0,
        "content_length_penalty": _content_length_penalty(candidate),
    }

    raw_score = sum(score_breakdown.values())
    algorithm_score = round(max(0, min(100, raw_score)), 2)

    result = ScoreResult(
        candidate=candidate,
        algorithm_score=algorithm_score,
        score_breakdown=score_breakdown,
        final_score=algorithm_score,
    )
    return result.model_dump(mode="json")


def _duplicate_canonical_urls(items: list[dict]) -> set[str]:
    counts = Counter(x.get("canonical_url", "") for x in items if x.get("canonical_url"))
    return {url for url, count in counts.items() if count > 1}


def _select_with_online_quota(
    scored_candidates: list[dict],
    top_k: int,
    min_online_k: int = 0,
) -> list[dict]:
    if top_k <= 0:
        return []

    selected_indexes = list(range(min(top_k, len(scored_candidates))))
    selected_set = set(selected_indexes)

    target_online = min(max(min_online_k, 0), top_k)
    online_count = sum(
        1 for idx in selected_indexes
        if _is_online_candidate(scored_candidates[idx])
    )

    if online_count < target_online:
        for idx, item in enumerate(scored_candidates):
            if idx in selected_set or not _is_online_candidate(item):
                continue
            selected_indexes.append(idx)
            selected_set.add(idx)
            online_count += 1
            if online_count >= target_online:
                break

    while len(selected_indexes) > top_k:
        removable = [
            idx for idx in selected_indexes
            if not _is_online_candidate(scored_candidates[idx])
        ]
        if not removable:
            removable = selected_indexes
        drop_idx = max(removable)
        selected_indexes.remove(drop_idx)
        selected_set.remove(drop_idx)

    return [scored_candidates[idx] for idx in sorted(selected_indexes)]


def _is_online_candidate(scored_candidate: dict) -> bool:
    candidate = scored_candidate.get("candidate", {})
    url = candidate.get("canonical_url") or candidate.get("url") or ""
    return str(url).startswith(("http://", "https://"))


def _duplicate_content_hashes(items: list[dict]) -> set[str]:
    counts = Counter(x.get("content_hash", "") for x in items if x.get("content_hash"))
    return {content_hash for content_hash, count in counts.items() if count > 1}


def _keywords(query: str) -> list[str]:
    parts = re.split(r"[\s,，;；|/]+", query.lower())
    return [p.strip() for p in parts if len(p.strip()) >= 2]


def _keyword_coverage(query: str, text: str) -> float:
    kws = _keywords(query)
    if not kws:
        return 0.0

    text = (text or "").lower()
    hit = sum(1 for kw in kws if kw in text)
    return hit / len(kws)


def _date_score(publish_date: str | None, start: str, end: str) -> float:
    if not publish_date:
        return 0

    try:
        d = date.fromisoformat(publish_date)
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        return 0

    if s <= d <= e:
        return 25

    return -15


def _section_hint_score(section_hint: str, section_id: str) -> float:
    if not section_hint:
        return 0
    if section_hint == section_id:
        return 30
    if section_hint in {"all", "*"}:
        return 10
    return -20


def _content_length_penalty(candidate: EnrichedCandidate) -> float:
    if candidate.file_ext == ".pdf" or "pdf" in candidate.content_type.lower():
        return 0

    body_len = len(candidate.body_text or "")
    if body_len == 0:
        return -15
    if body_len < 300:
        return -8
    return 0


def _simple_source_type(source_type_hint: str) -> SourceType:
    hint = (source_type_hint or "").strip().lower()
    if not hint or hint in {"html", "pdf", "url"}:
        return SourceType.UNKNOWN
    if hint in {x.value for x in SourceType}:
        return SourceType(hint)
    return SourceType.UNKNOWN


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "是"}


def _title_from_tags_or_note(row: dict) -> str:
    tags = (row.get("tags") or "").strip()
    if tags:
        return tags.split(",")[0].strip()

    note = (row.get("note") or "").strip()
    if note:
        return note.split("|")[0].strip()

    return ""


def _resolve_manual_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path

    if path.exists():
        return path

    project_path = Path(__file__).resolve().parents[1] / path
    if project_path.exists():
        return project_path

    return path


def _save_section_debug(run_paths: dict, section_id: str, name: str, data: list[dict]) -> None:
    queue_dir = Path(run_paths["queue"])
    queue_dir.mkdir(parents=True, exist_ok=True)
    path = queue_dir / f"{section_id}_{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
