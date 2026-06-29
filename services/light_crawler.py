from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

from schemas import CrawledContent
from services.url_normalizer import normalize_url


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 ESGDemoBot/0.1"
}


class LightCrawler:
    def __init__(self, cache_dir: str | Path = "runs/_cache/manual_crawl"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def crawl(self, url: str, use_cache: bool = True) -> dict:
        canonical = normalize_url(url)
        cache_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"

        if use_cache and cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        try:
            result = self._crawl_uncached(url, canonical)
        except Exception as e:
            result = CrawledContent(
                url=url,
                canonical_url=canonical,
                source_name=urlparse(canonical).netloc,
                crawl_failed=True,
                error=str(e),
            )

        data = result.model_dump(mode="json")
        cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def _crawl_uncached(self, url: str, canonical: str) -> CrawledContent:
        parsed = urlparse(canonical)
        source_name = parsed.netloc

        if parsed.scheme.lower() == "file":
            return self._crawl_local_file(url, canonical)

        if canonical.lower().endswith(".pdf"):
            return CrawledContent(
                url=url,
                canonical_url=canonical,
                title=_title_from_url(canonical),
                snippet="PDF document",
                body_text="",
                publish_date=None,
                source_name=source_name,
                content_type="application/pdf",
                file_ext=".pdf",
                content_hash="",
                crawl_failed=False,
            )

        resp = requests.get(canonical, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        snippet = _extract_meta_description(soup)

        body = trafilatura.extract(
            html,
            output_format="txt",
            include_links=False,
            include_tables=True,
        ) or ""

        publish_date = (
            _extract_meta_date(soup)
            or _extract_date_from_text(title)
            or _extract_date_from_text(body[:2000])
        )

        content_hash = hashlib.sha256(body[:5000].encode("utf-8", errors="ignore")).hexdigest() if body else ""

        return CrawledContent(
            url=url,
            canonical_url=canonical,
            title=title[:300],
            snippet=snippet[:500],
            body_text=body[:8000],
            publish_date=publish_date,
            source_name=source_name,
            content_type=content_type,
            file_ext=".html",
            content_hash=content_hash,
            crawl_failed=False,
        )

    def _crawl_local_file(self, url: str, canonical: str) -> CrawledContent:
        parsed = urlparse(canonical)
        file_path = Path(unquote(parsed.path))
        source_name = "local"

        if not file_path.exists():
            raise FileNotFoundError(str(file_path))

        suffix = file_path.suffix.lower()
        content_type = mimetypes.guess_type(str(file_path))[0] or ""

        if suffix == ".pdf":
            return CrawledContent(
                url=url,
                canonical_url=canonical,
                title=file_path.stem,
                snippet="PDF document",
                body_text="",
                publish_date=None,
                source_name=source_name,
                content_type=content_type or "application/pdf",
                file_ext=".pdf",
                content_hash="",
                crawl_failed=False,
            )

        html = file_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        snippet = _extract_meta_description(soup)

        body = trafilatura.extract(
            html,
            output_format="txt",
            include_links=False,
            include_tables=True,
        ) or soup.get_text("\n", strip=True)

        publish_date = (
            _extract_meta_date(soup)
            or _extract_date_from_text(title)
            or _extract_date_from_text(body[:2000])
        )

        content_hash = hashlib.sha256(body[:5000].encode("utf-8", errors="ignore")).hexdigest() if body else ""

        return CrawledContent(
            url=url,
            canonical_url=canonical,
            title=(title or file_path.stem)[:300],
            snippet=snippet[:500],
            body_text=body[:8000],
            publish_date=publish_date,
            source_name=source_name,
            content_type=content_type or "text/html",
            file_ext=suffix or ".html",
            content_hash=content_hash,
            crawl_failed=False,
        )


def _title_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or url


def _extract_meta_description(soup: BeautifulSoup) -> str:
    selectors = [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ]

    for attrs in selectors:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()

    return ""


def _extract_meta_date(soup: BeautifulSoup) -> str | None:
    attrs_list = [
        {"property": "article:published_time"},
        {"name": "publishdate"},
        {"name": "pubdate"},
        {"name": "date"},
        {"itemprop": "datePublished"},
    ]

    for attrs in attrs_list:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return _normalize_date(tag["content"])

    return None


def _extract_date_from_text(text: str) -> str | None:
    if not text:
        return None

    patterns = [
        r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})",
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    return None


def _normalize_date(raw: str) -> str | None:
    raw = raw.strip()

    m = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", raw)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    return None
