# services/mineru_parser.py
from __future__ import annotations

import subprocess
from pathlib import Path

from config import MINERU_CMD
from schemas import FetchResult, ParsedDoc, ParserType, ParseStatus


def parse_pdf_with_mineru(fetch_result: FetchResult, run_paths: dict) -> ParsedDoc:
    pdf_path = fetch_result.official_pdf_path
    output_dir = run_paths["parsed"] / fetch_result.url_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [MINERU_CMD, "-p", pdf_path, "-o", str(output_dir)],
            check=True,
            timeout=180,
        )

        md_files = list(output_dir.rglob("*.md"))
        json_files = list(output_dir.rglob("*.json"))

        if not md_files:
            raise RuntimeError("MinerU did not generate markdown file")

        md_path = md_files[0]
        text = md_path.read_text(encoding="utf-8", errors="ignore")

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
            parser=ParserType.MINERU,
            status=ParseStatus.SUCCESS,
            markdown_path=str(md_path),
            json_path=str(json_files[0]) if json_files else "",
            text_length=len(text),
        )

    except Exception as e:
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
            parser=ParserType.MINERU,
            status=ParseStatus.FAILED,
            error=str(e),
        )