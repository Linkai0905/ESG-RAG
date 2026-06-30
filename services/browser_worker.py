# services/browser_worker.py
from __future__ import annotations

import json
import mimetypes
import shutil
import requests
from pathlib import Path
from urllib.parse import unquote, urlparse
from playwright.sync_api import sync_playwright

from schemas import UrlQueueItem, FetchResult, FetchStatus


def fetch_batch(url_queue: list[dict], run_paths: dict) -> list[dict]:
    results = []

    for raw in url_queue:
        item = UrlQueueItem.model_validate(raw)
        try:
            result = fetch_one(item, run_paths)
        except Exception as e:
            result = FetchResult(
                url_id=item.url_id,
                original_url=item.original_url,
                canonical_url=item.canonical_url,
                section=item.section,
                source_type=item.source_type,
                source_name=item.source_name,
                publish_date=item.publish_date,
                status=FetchStatus.FAILED,
                error=str(e),
            )

        results.append(result.model_dump(mode="json"))

    return results


def fetch_one(item: UrlQueueItem, run_paths: dict) -> FetchResult:
    url = item.canonical_url

    if urlparse(url).scheme.lower() == "file":
        return _fetch_local_file(item, run_paths)

    if url.lower().endswith(".pdf"):
        return _download_pdf(item, run_paths)

    last_error = None
    for fetch_url in _browser_url_candidates(url):
        try:
            return _fetch_html_with_browser(item, run_paths, fetch_url)
        except Exception as e:
            last_error = e
            if _should_try_http_fallback(fetch_url, e):
                continue
            raise

    raise last_error or RuntimeError(f"Failed to fetch {url}")


def _fetch_html_with_browser(
    item: UrlQueueItem,
    run_paths: dict,
    fetch_url: str,
) -> FetchResult:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1365, "height": 900},
            user_agent="Mozilla/5.0 ESGDemoBot/0.1",
        )

        try:
            response = page.goto(fetch_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)

            content_type = response.headers.get("content-type", "") if response else ""
            http_status = response.status if response else None

            if "application/pdf" in content_type.lower():
                browser.close()
                return _download_pdf(item, run_paths)

            title = page.title()
            html = page.content()

            raw_html_path = run_paths["raw"] / f"{item.url_id}.html"
            raw_html_path.write_text(html, encoding="utf-8", errors="ignore")

            print_pdf_path = run_paths["raw"] / f"{item.url_id}.print.pdf"
            try:
                page.pdf(path=str(print_pdf_path), format="A4", print_background=True)
            except Exception:
                print_pdf_path = ""

            screenshot_path = run_paths["raw"] / f"{item.url_id}.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                screenshot_path = ""

            result = FetchResult(
                url_id=item.url_id,
                original_url=item.original_url,
                canonical_url=item.canonical_url,
                final_url=page.url,
                parent_url=item.parent_url,
                section=item.section,
                source_type=item.source_type,
                source_name=item.source_name,
                publish_date=item.publish_date,
                status=FetchStatus.SUCCESS,
                http_status=http_status,
                content_type=content_type or "text/html",
                file_ext=".html",
                title=title or item.title,
                raw_html_path=str(raw_html_path),
                print_pdf_path=str(print_pdf_path),
                screenshot_path=str(screenshot_path),
            )

            _save_meta(result, run_paths)
            return result

        finally:
            browser.close()


def _browser_url_candidates(url: str) -> list[str]:
    if url.lower().startswith("https://"):
        return [url, "http://" + url[8:]]
    return [url]


def _should_try_http_fallback(fetch_url: str, error: Exception) -> bool:
    if not fetch_url.lower().startswith("https://"):
        return False

    text = str(error)
    return (
        "ERR_SSL_VERSION_OR_CIPHER_MISMATCH" in text
        or "SSL" in text
        or "handshake" in text.lower()
    )


def _fetch_local_file(item: UrlQueueItem, run_paths: dict) -> FetchResult:
    parsed = urlparse(item.canonical_url)
    file_path = Path(unquote(parsed.path))

    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    suffix = file_path.suffix.lower()
    content_type = mimetypes.guess_type(str(file_path))[0] or ""

    if suffix == ".pdf":
        pdf_path = run_paths["raw"] / f"{item.url_id}.pdf"
        shutil.copyfile(file_path, pdf_path)

        result = FetchResult(
            url_id=item.url_id,
            original_url=item.original_url,
            canonical_url=item.canonical_url,
            final_url=item.canonical_url,
            parent_url=item.parent_url,
            section=item.section,
            source_type=item.source_type,
            source_name=item.source_name,
            publish_date=item.publish_date,
            status=FetchStatus.SUCCESS,
            http_status=None,
            content_type=content_type or "application/pdf",
            file_ext=".pdf",
            title=item.title,
            official_pdf_path=str(pdf_path),
        )
        _save_meta(result, run_paths)
        return result

    raw_html_path = run_paths["raw"] / f"{item.url_id}.html"

    if suffix in [".html", ".htm"]:
        shutil.copyfile(file_path, raw_html_path)
    else:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        raw_html_path.write_text(
            "<html><body><article>\n"
            + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "\n</article></body></html>",
            encoding="utf-8",
        )

    result = FetchResult(
        url_id=item.url_id,
        original_url=item.original_url,
        canonical_url=item.canonical_url,
        final_url=item.canonical_url,
        parent_url=item.parent_url,
        section=item.section,
        source_type=item.source_type,
        source_name=item.source_name,
        publish_date=item.publish_date,
        status=FetchStatus.SUCCESS,
        http_status=None,
        content_type=content_type or "text/html",
        file_ext=".html",
        title=item.title,
        raw_html_path=str(raw_html_path),
    )
    _save_meta(result, run_paths)
    return result


def _download_pdf(item: UrlQueueItem, run_paths: dict) -> FetchResult:
    resp = requests.get(item.canonical_url, timeout=60)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "application/pdf")
    ext = ".pdf"

    pdf_path = run_paths["raw"] / f"{item.url_id}{ext}"
    pdf_path.write_bytes(resp.content)

    result = FetchResult(
        url_id=item.url_id,
        original_url=item.original_url,
        canonical_url=item.canonical_url,
        final_url=item.canonical_url,
        parent_url=item.parent_url,
        section=item.section,
        source_type=item.source_type,
        source_name=item.source_name,
        publish_date=item.publish_date,
        status=FetchStatus.SUCCESS,
        http_status=resp.status_code,
        content_type=content_type,
        file_ext=ext,
        title=item.title,
        official_pdf_path=str(pdf_path),
    )

    _save_meta(result, run_paths)
    return result


def _save_meta(result: FetchResult, run_paths: dict) -> None:
    meta_path = run_paths["meta"] / f"{result.url_id}.json"
    meta_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
