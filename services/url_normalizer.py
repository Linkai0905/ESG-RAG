# services/url_normalizer.py
from __future__ import annotations

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from schemas import UrlCandidate, UrlQueueItem


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "from",
    "source",
}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    query_items = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=False):
        if k.lower() not in TRACKING_PARAMS:
            query_items.append((k, v))

    clean_query = urlencode(query_items, doseq=True)

    return urlunparse((
        scheme,
        netloc,
        parsed.path,
        "",
        clean_query,
        "",
    ))


def candidates_to_queue(candidates: list[dict]) -> list[dict]:
    queue: dict[str, UrlQueueItem] = {}

    for raw in candidates:
        candidate = UrlCandidate.model_validate(raw)
        canonical = normalize_url(candidate.url)

        item = UrlQueueItem.from_candidate(
            candidate=candidate,
            canonical_url=canonical,
        )

        old = queue.get(item.url_id)
        if old is None or item.priority > old.priority:
            queue[item.url_id] = item

    return [x.model_dump(mode="json") for x in queue.values()]