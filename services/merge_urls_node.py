from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from schemas import RankedUrlCandidate, SectionType, UrlCandidate, UrlQueueItem, sha256_text


def merge_urls_node(state: dict) -> dict:
    """
    全局 URL 合并节点。

    输入:
        state["url_candidates"]

    输出:
        state["url_queue"]

    Search Agent 不直接写 url_queue；只有本节点负责生成最终抓取队列。
    """
    run_paths = _normalize_run_paths(state["run_paths"])
    queue_dir = Path(run_paths["queue"])
    queue_dir.mkdir(parents=True, exist_ok=True)

    raw_candidates = state.get("url_candidates", [])

    candidates = []
    errors = []

    for raw in raw_candidates:
        try:
            candidates.append(_validate_ranked_candidate(raw))
        except Exception as e:
            errors.append({
                "stage": "merge_urls_validate_candidate",
                "error": str(e),
                "raw": raw,
            })

    _save_json(
        queue_dir / "url_candidates.json",
        [c.model_dump(mode="json") for c in candidates],
    )

    grouped: dict[str, list[RankedUrlCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.canonical_url].append(candidate)

    merged_queue = []
    for canonical_url, group in grouped.items():
        best = _pick_best_candidate(group)

        section_tags = sorted({x.section for x in group})
        discovered_by = sorted({x.discovered_by for x in group if x.discovered_by})
        queries = sorted({x.query for x in group if x.query})

        max_score = max(x.final_score for x in group)
        pinned = any(x.pinned for x in group)

        item = UrlQueueItem(
            url_id=sha256_text(canonical_url)[:16],
            canonical_url=canonical_url,
            original_url=best.url,
            title=best.title,
            snippet=best.snippet,
            section=SectionType(best.section),
            source_type=best.source_type,
            publish_date=best.publish_date,
            source_name=best.source_name,
            priority=min(100, max(0, int(max_score))),
            discovered_by=",".join(discovered_by) or best.discovered_by or "search_agent",
            query=" | ".join(queries),
            confidence=min(1.0, max_score / 100) if max_score else 0.5,
            is_manual=best.origin == "manual",
            pinned=pinned,
            manual_priority=best.priority,
            algorithm_score=best.algorithm_score,
            agent_score=best.agent_score,
            final_score=max_score,
            score_breakdown=best.score_breakdown,
            agent_reason=best.agent_reason,
            tags=best.tags,
            section_tags=",".join(section_tags),
            merged_candidate_count=len(group),
        )

        merged_queue.append(item.model_dump(mode="json"))

    merged_queue.sort(
        key=lambda x: (
            x.get("pinned", False),
            x.get("final_score") or 0,
            x.get("priority") or 0,
        ),
        reverse=True,
    )

    max_fetch_urls = state.get("max_fetch_urls", 60)
    url_queue = merged_queue[:max_fetch_urls]

    _save_json(queue_dir / "url_queue.json", url_queue)

    merge_metrics = {
        "url_candidate_count": len(candidates),
        "unique_url_count": len(grouped),
        "url_queue_count": len(url_queue),
        "duplicate_url_count": len(candidates) - len(grouped),
        "pinned_count": sum(1 for x in url_queue if x.get("pinned")),
        "section_counts_in_candidates": _count_sections(candidates),
        "section_counts_in_queue": _count_queue_sections(url_queue),
    }

    _save_json(queue_dir / "url_metrics.json", merge_metrics)

    metrics = dict(state.get("metrics", {}))
    metrics.update(merge_metrics)
    metrics["merge_urls"] = merge_metrics

    return {
        "url_queue": url_queue,
        "metrics": metrics,
        "errors": errors,
    }


def _validate_ranked_candidate(raw: dict) -> RankedUrlCandidate:
    try:
        return RankedUrlCandidate.model_validate(raw)
    except Exception:
        legacy = UrlCandidate.model_validate(raw)
        final_score = legacy.final_score if legacy.final_score is not None else legacy.priority
        return RankedUrlCandidate(
            candidate_id=sha256_text(legacy.url),
            url_id=sha256_text(legacy.url)[:16],
            url=legacy.url,
            canonical_url=legacy.url,
            title=legacy.title,
            snippet=legacy.snippet,
            section=legacy.section.value if hasattr(legacy.section, "value") else str(legacy.section),
            section_hint=legacy.section.value if hasattr(legacy.section, "value") else str(legacy.section),
            publish_date=legacy.publish_date,
            source_name=legacy.source_name,
            source_type=legacy.source_type,
            origin="ai_search",
            query=legacy.query,
            discovered_by=legacy.discovered_by,
            pinned=legacy.pinned,
            priority=legacy.manual_priority,
            algorithm_score=legacy.algorithm_score,
            agent_score=legacy.agent_score,
            final_score=final_score,
            score_breakdown=legacy.score_breakdown,
            agent_reason=legacy.agent_reason,
            tags=legacy.tags,
            content_type="",
            file_ext=".pdf" if legacy.url.lower().endswith(".pdf") else "",
        )


def _pick_best_candidate(group: list[RankedUrlCandidate]) -> RankedUrlCandidate:
    return sorted(
        group,
        key=lambda x: (
            x.pinned,
            x.final_score,
            x.algorithm_score,
        ),
        reverse=True,
    )[0]


def _count_sections(candidates: list[RankedUrlCandidate]) -> dict:
    counts = defaultdict(int)
    for candidate in candidates:
        counts[candidate.section] += 1
    return dict(counts)


def _count_queue_sections(queue: list[dict]) -> dict:
    counts = defaultdict(int)
    for item in queue:
        counts[item.get("section", "unknown")] += 1
    return dict(counts)


def _save_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_run_paths(run_paths: dict) -> dict:
    return {k: str(v) for k, v in run_paths.items()}
