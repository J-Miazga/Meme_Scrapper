from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from typing import Dict, List, Optional
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
WEBSITE_URL = os.environ.get("WEBSITE_URL")
CHECKPOINT_SIZE = 5

# Debug checkpoint for "already sent" memes.
# For now, fill these manually with IDs from previous successful session.
LAST_SESSION_MEME_IDS: List[int] = [
    4394878,
    4395133,
    4395078,
    4394556,
    4394824
]

def make_browser() -> tuple[Playwright, Browser, BrowserContext, Page]:
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="pl-PL",
    )
    page = context.new_page()
    return playwright, browser, context, page


def fetch_html_with_retry(
    page: Page,
    url: str,
    retries: int = 3,
    retry_sleep_seconds: float = 1.0,
) -> str:
    last_error: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector("article.article")
            return page.content()
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(retry_sleep_seconds)

    raise RuntimeError(f"Failed to fetch URL after {retries} attempts: {url}") from last_error


def _pick_from_srcset(srcset: str) -> Optional[str]:
    if not srcset:
        return None
    first = srcset.split(",")[0].strip()
    if not first:
        return None
    return first.split(" ")[0].strip()


def _extract_src(tag) -> Optional[str]:
    return (
        tag.get("src")
        or tag.get("data-src")
        or tag.get("data-original")
        or tag.get("data-lazy")
        or _pick_from_srcset(tag.get("srcset", ""))
    )


def _unique_append(items: List[str], value: Optional[str]) -> None:
    if not value:
        return
    if value not in items:
        items.append(value)


def _parse_paged_url(url: str) -> tuple[str, int, str]:
    match = re.match(r"^(.*?/str/)(\d+)(.*)$", url)
    if not match:
        raise ValueError(
            "URL must contain '/str/<page_number>'"
        )
    prefix, page_text, suffix = match.groups()
    return prefix, int(page_text), suffix


def _normalize_key(value: object) -> str:
    return str(value).strip()


def _meme_key(meme: Dict[str, object]) -> str:
    meme_id = meme.get("id")
    if meme_id:
        return _normalize_key(meme_id)
    canonical = json.dumps(
        meme.get("ordered_content", []), ensure_ascii=False, sort_keys=True
    )
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def scrape_memes(soup: BeautifulSoup) -> List[Dict[str, object]]:
    memes: List[Dict[str, object]] = []
    for article in soup.select("article.article"):
        images: List[str] = []
        videos: List[str] = []
        texts: List[str] = []
        ordered_content: List[Dict[str, str]] = []

        # Combined selector keeps document order inside this article.
        for node in article.select(
            "img.article-image, .video-player source, div.article-description"
        ):
            if node.name == "img":
                src = _extract_src(node)
                if src:
                    ordered_content.append({"type": "image", "value": src})
                    _unique_append(images, src)
            elif node.name == "source":
                src = _extract_src(node)
                if src:
                    ordered_content.append({"type": "video", "value": src})
                    _unique_append(videos, src)
            else:
                text = node.get_text(strip=True)
                if text:
                    ordered_content.append({"type": "text", "value": text})
                    texts.append(text)

        types: List[str] = []
        for item in ordered_content:
            item_type = item["type"]
            if item_type not in types:
                types.append(item_type)

        meme_id = article.get("data-content-id") or article.get("id")
        memes.append(
            {
                "id": meme_id,
                "types": types,
                "combination": "+".join(types) if types else "unknown",
                "ordered_content": ordered_content,
                "texts": texts,
                "images": images,
                "videos": videos,
            }
        )
    return memes


def scrape_until_known(
    base_url: str,
    delay_seconds: float,
    known_keys: set[str],
    max_pages: int,
) -> Dict[str, object]:
    prefix, start_page, suffix = _parse_paged_url(base_url)

    all_new_memes: List[Dict[str, object]] = []
    fetched_pages = 0
    stop_key: Optional[str] = None
    stop_page: Optional[int] = None

    playwright, browser, context, page = make_browser()
    try:
        for page_number in range(start_page, start_page + max_pages):
            page_url = f"{prefix}{page_number}{suffix}"
            html = fetch_html_with_retry(page, page_url)
            soup = BeautifulSoup(html, "html.parser")
            page_memes = scrape_memes(soup)
            fetched_pages += 1

            if not page_memes:
                break

            for meme in page_memes:
                meme["source_page"] = page_number
                meme["source_url"] = page_url

                key = _meme_key(meme)
                meme["key"] = key

                if key in known_keys:
                    stop_key = key
                    stop_page = page_number
                    return {
                        "memes": all_new_memes,
                        "fetched_pages": fetched_pages,
                        "stop_key": stop_key,
                        "stop_page": stop_page,
                    }

                all_new_memes.append(meme)

            if delay_seconds > 0:
                time.sleep(delay_seconds)
    finally:
        context.close()
        browser.close()
        playwright.stop()

    return {
        "memes": all_new_memes,
        "fetched_pages": fetched_pages,
        "stop_key": stop_key,
        "stop_page": stop_page,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape memes from website.")
    parser.add_argument(
        "--url",
        default=os.environ.get("WEBSITE_URL"),
        help="Page URL to scrape",
    )
    parser.add_argument(
        "--out",
        default="images.json",
        help="Output JSON filename (default: images.json)",
    )
    parser.add_argument(
        "--no-save-json",
        action="store_true",
        help="Do not save results to JSON file.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay in seconds before the request (default: 2.0)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Maximum number of paginated pages to scan (default: 20).",
    )
    args = parser.parse_args()

    try:
        known_keys_input = [
            _normalize_key(item)
            for item in LAST_SESSION_MEME_IDS[:CHECKPOINT_SIZE]
            if _normalize_key(item)
        ]
        known_keys = set(known_keys_input)
        result = scrape_until_known(
            base_url=args.url,
            delay_seconds=args.delay,
            known_keys=known_keys,
            max_pages=args.max_pages,
        )
        memes = result["memes"]
    except (PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
        print(f"Error fetching {args.url}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    checkpoint_candidates = [_meme_key(meme) for meme in memes[:CHECKPOINT_SIZE]]
    if not checkpoint_candidates:
        checkpoint_candidates = known_keys_input
    payload = {
        "source_url_start": args.url,
        "fetched_pages": result["fetched_pages"],
        "stopped_on_known_key": result["stop_key"],
        "stopped_on_page": result["stop_page"],
        "known_keys_input": known_keys_input,
        "checkpoint_candidates_next_run": checkpoint_candidates,
        "memes_on_page": len(memes),
        "memes": memes,
    }

    if not args.no_save_json:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"Found {len(memes)} new meme(s) after scanning {result['fetched_pages']} page(s)."
    )
    for idx, meme in enumerate(memes, start=1):
        print(
            f"{idx}. meme id={meme.get('id')} combination={meme.get('combination')} "
            f"types={meme.get('types')} source_page={meme.get('source_page')}"
        )
    if result["stop_key"]:
        print(
            f"Stopped on known meme key={result['stop_key']} "
            f"at page={result['stop_page']}."
        )
    else:
        print("No known meme key encountered within page scan limit.")

    print(f"Next run checkpoint suggestion (first/newest {CHECKPOINT_SIZE} IDs):")
    print(checkpoint_candidates)

    if not args.no_save_json:
        print(f"Saved {len(memes)} meme(s) to {args.out}")
    else:
        print("JSON saving disabled by --no-save-json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
