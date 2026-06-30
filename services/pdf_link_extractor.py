# services/pdf_link_extractor.py
from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from schemas import FetchResult, UrlCandidate, SourceType


def extract_pdf_candidates(fetch_result: FetchResult) -> list[dict]:
    if not fetch_result.raw_html_path:
        return []

    html = Path(fetch_result.raw_html_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    candidates = []

    for a in soup.find_all("a"):
        href = a.get("href") or ""
        text = a.get_text(" ", strip=True)

        if ".pdf" not in href.lower():
            continue

        pdf_url = urljoin(fetch_result.final_url or fetch_result.canonical_url, href)

        item = UrlCandidate(
            url=pdf_url,
            title=text or fetch_result.title,
            snippet="PDF attachment discovered from HTML source",
            source_name=fetch_result.source_name,
            publish_date=fetch_result.publish_date,
            section=fetch_result.section,
            source_type=fetch_result.source_type or SourceType.UNKNOWN,
            query="pdf_link_extractor",
            discovered_by="pdf_link_extractor",
            confidence=0.7,
            requires_browser=True,
            requires_mineru=True,
            priority=fetch_result.source_type == SourceType.ANNOUNCEMENT and 95 or 80,
            reason=f"PDF attachment discovered from parent source: {fetch_result.final_url}",
        )

        candidates.append(item.model_dump(mode="json"))

    return candidates
