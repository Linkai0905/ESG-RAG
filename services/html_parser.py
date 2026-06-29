# services/html_parser.py
from __future__ import annotations

from pathlib import Path
import trafilatura

from schemas import FetchResult, ParsedDoc, ParserType, ParseStatus


def parse_html_to_markdown(fetch_result: FetchResult, run_paths: dict) -> ParsedDoc:
    html_path = Path(fetch_result.raw_html_path)
    html = html_path.read_text(encoding="utf-8", errors="ignore")

    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
    )

    if not text or len(text.strip()) < 100:
        text = fetch_result.title or ""

    md_path = run_paths["parsed"] / f"{fetch_result.url_id}.clean.md"
    md_path.write_text(text, encoding="utf-8")

    return ParsedDoc(
        doc_id=fetch_result.url_id,
        url_id=fetch_result.url_id,
        source_url=fetch_result.final_url or fetch_result.canonical_url,
        parent_url=fetch_result.parent_url,
        title=fetch_result.title,
        section=fetch_result.section,
        source_type=fetch_result.source_type,
        source_name=fetch_result.source_name,
        publish_date=fetch_result.publish_date,
        parser=ParserType.HTML,
        status=ParseStatus.SUCCESS,
        markdown_path=str(md_path),
        text_length=len(text),
    )