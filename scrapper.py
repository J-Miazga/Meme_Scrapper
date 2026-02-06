from __future__ import annotations

import argparse
import json
from pydoc import html
import sys
import time
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright
import dotenv

from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
WEBSITE_URL = dotenv.get_key(".env", "WEBSITE_URL")

def fetch_html_js(url: str, delay_seconds: float) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="pl-PL",
        )

        page = context.new_page()
        page.goto(url, wait_until="load")

        html = page.content()

        browser.close()
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    return html


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


def scrape_memes(soup: BeautifulSoup) -> List[Dict[str, object]]:
    memes: List[Dict[str, object]] = []
    for article in soup.select("article.article"):
        images: List[str] = []
        videos: List[str] = []
        texts: List[str] = []

        for img in article.select("img.article-image"):
            _unique_append(images, _extract_src(img))

        for source in article.select(".video-player source"):
            _unique_append(videos, _extract_src(source))

        for desc in article.select("div.article-description"):
            text = desc.get_text(strip=True)
            if text:
                texts.append(text)

        types: List[str] = []
        if texts:
            types.append("text")
        if images:
            types.append("image")
        if videos:
            types.append("video")

        meme_id = article.get("data-content-id") or article.get("id")
        memes.append(
            {
                "id": meme_id,
                "types": types,
                "combination": "+".join(types) if types else "unknown",
                "texts": texts,
                "images": images,
                "videos": videos,
            }
        )
    return memes


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape .jpeg image links from JBZD.")
    parser.add_argument(
        "--url",
        default=WEBSITE_URL,
        help="Page URL to scrape",
    )
    parser.add_argument(
        "--out",
        default="images.json",
        help="Output JSON filename (default: images.json)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay in seconds before the request (default: 2.0)",
    )
    args = parser.parse_args()

    try:
        html = fetch_html_js(args.url, args.delay)
        soup = BeautifulSoup(html, "html.parser")
        memes = scrape_memes(soup)
    except (HTTPError, URLError) as exc:
        print(f"Error fetching {args.url}: {exc}", file=sys.stderr)
        return 1

    payload = {
        "source_url": args.url,
        "memes_on_page": len(memes),
        "memes": memes,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Found {len(memes)} meme(s) on page.")
    for idx, meme in enumerate(memes, start=1):
        print(
            f"{idx}. meme id={meme.get('id')} combination={meme.get('combination')} "
            f"types={meme.get('types')}"
        )
    print(f"Saved {len(memes)} meme(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
