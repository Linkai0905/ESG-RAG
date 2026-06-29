# services/search_api.py
from __future__ import annotations

import csv
import requests
from pathlib import Path
from typing import Any, Dict, List

from config import SEARCH_PROVIDER, SEARCH_API_KEY


def search_web(
    query: str,
    start_date: str,
    end_date: str,
    top_k: int = 5,
    section: str | None = None,
) -> List[Dict[str, Any]]:
    if SEARCH_PROVIDER == "tavily":
        return _search_tavily(query, top_k)

    return _search_manual(query, top_k, section=section)


def _search_tavily(query: str, top_k: int) -> List[Dict[str, Any]]:
    if not SEARCH_API_KEY:
        return []

    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": SEARCH_API_KEY,
            "query": query,
            "max_results": top_k,
            "include_answer": False,
            "include_raw_content": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("results", []):
        results.append({
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "snippet": item.get("content", ""),
            "source_name": "",
            "publish_date": None,
            "query": query,
        })

    return results


def _search_manual(
    query: str,
    top_k: int,
    section: str | None = None,
) -> List[Dict[str, Any]]:
    path = Path("manual_sources.csv")
    if not path.exists():
        return []

    results = []

    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            row_section = (row.get("section") or "").strip()
            if section and row_section != section:
                continue

            source_type = (row.get("source_type") or "url").strip().lower()
            url = (row.get("url") or "").strip()
            local_path = (row.get("local_path") or "").strip()

            is_local = bool(local_path)

            if is_local:
                file_path = Path(local_path).expanduser()
                if not file_path.is_absolute():
                    file_path = Path.cwd() / file_path

                if not file_path.exists():
                    continue

                url = file_path.as_uri()
                local_path = str(file_path)

                if source_type == "url":
                    suffix = file_path.suffix.lower()
                    if suffix == ".pdf":
                        source_type = "pdf"
                    elif suffix in [".html", ".htm"]:
                        source_type = "html"
                    elif suffix in [".md", ".markdown"]:
                        source_type = "markdown"
                    else:
                        source_type = "file"

            results.append({
                "section": row_section,
                "source_type": source_type,
                "is_local": is_local,
                "local_path": local_path,
                "url": url,
                "title": row.get("title", ""),
                "snippet": row.get("snippet", ""),
                "source_name": row.get("source_name", ""),
                "publish_date": row.get("publish_date") or None,
                "query": query,
            })

    return results[:top_k]
