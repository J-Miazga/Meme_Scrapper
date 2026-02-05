#!/usr/bin/env python3
"""
Simple HTML scraper for jbzd.com.pl that collects image URLs from one page
and writes them to a JSON file.

Uses only the standard library (urllib + html.parser).
"""

from __future__ import annotations

import argparse
import json
from pydoc import html
import sys
import time
from typing import List, Optional
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


def scrape_images(url: str, delay_seconds: float) -> List[str]:
    html = fetch_html_js(url,delay_seconds)
    soup = BeautifulSoup(html, "html.parser")
    images: List[str] = []
    for img in soup.select("img.article-image"):
        _unique_append(images, _extract_src(img))
    return images


def scrape_videos(url: str, delay_seconds: float) -> List[str]:
    html = fetch_html_js(url,delay_seconds)
    soup = BeautifulSoup(html, "html.parser")
    videos: List[str] = []
    for source in soup.select(".video-player source"):
        src = _extract_src(source)
        _unique_append(videos, src)
    
    return videos


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
        images = scrape_images(args.url, args.delay)
        videos = scrape_videos(args.url, args.delay)
    except (HTTPError, URLError) as exc:
        print(f"Error fetching {args.url}: {exc}", file=sys.stderr)
        return 1

    payload = {
        "source_url": args.url,
        "count": len(images) + len(videos),
        "images": images,
        "videos": videos,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(images + videos)} link(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
