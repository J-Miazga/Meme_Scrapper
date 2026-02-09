from __future__ import annotations
import logging
import re
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
#from dotenv import load_dotenv
from bs4 import BeautifulSoup
from models import (
    DEFAULT_FETCH_RETRIES,
    DEFAULT_FETCH_SLEEP_SECONDS,
    USER_AGENT,
    Meme,
)


logger = logging.getLogger(__name__)


def make_browser() -> tuple[Playwright, Browser, BrowserContext, Page]:
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    try:
        logger.debug("Starting Playwright browser context.")
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="pl-PL",
        )
        page = context.new_page()
        logger.debug("Browser context started successfully.")
        return playwright, browser, context, page
    except Exception:
        logger.exception("Failed to initialize browser.")
        if context is not None:
            try:
                context.close()
            except Exception:
                logger.debug("Failed to close context after startup error.", exc_info=True)
        if browser is not None:
            try:
                browser.close()
            except Exception:
                logger.debug("Failed to close browser after startup error.", exc_info=True)
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                logger.debug("Failed to stop Playwright after startup error.", exc_info=True)
        raise


def fetch_html(
    page: Page,
    url: str,
    retries: int = DEFAULT_FETCH_RETRIES,
    retry_sleep_seconds: float = DEFAULT_FETCH_SLEEP_SECONDS,
) -> str:
    last_error: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            logger.debug("Fetching URL attempt %s/%s: %s",attempt,retries,url)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector("article.article")
            logger.debug("Fetched URL successfully on attempt %s: %s", attempt, url)
            return page.content()
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            last_error = exc
            logger.warning("Fetch attempt %s/%s failed for %s: %s",attempt,retries,url,exc)
            if attempt == retries:
                break
            time.sleep(retry_sleep_seconds)

    logger.error("Failed to fetch URL after %s attempts: %s", retries, url)
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


def _parse_paged_url(url: str) -> tuple[str, int, str]:
    match = re.match(r"^(.*?/str/)(\d+)(.*)$", url)
    if not match:
        logger.error("URL does not match expected pattern with '/str/<page_number>': %s", url)
        raise ValueError("URL must contain '/str/<page_number>'")
    prefix, page_text, suffix = match.groups()
    return prefix, int(page_text), suffix



def scrape_memes(soup: BeautifulSoup) -> List[Meme]:
    memes: List[Meme] = []
    articles = soup.select("article.article")
    logger.debug("Parsing memes from %s article nodes.", len(articles))
    for article in articles:
        ordered_content: List[Dict[str, str]] = []

        for node in article.select(
            "img.article-image, .video-player source, div.article-description"
        ):
            if node.name == "img":
                src = _extract_src(node)
                if src:
                    ordered_content.append({"type": "image", "value": src})
            elif node.name == "source":
                src = _extract_src(node)
                if src:
                    ordered_content.append({"type": "video", "value": src})
            else:
                text = node.get_text(strip=True)
                if text:
                    ordered_content.append({"type": "text", "value": text})

        meme_id = article.get("data-content-id") or article.get("id")
        meme = Meme(
            id=str(meme_id) if meme_id is not None else None,
            ordered_content=ordered_content,
        )
        memes.append(meme)
    logger.debug("Parsed %s meme objects from current page.", len(memes))
    return memes


def scrape_until_known(
    base_url: str,
    delay_seconds: float,
    known_ids: set[str],
    max_pages: int,
) -> List[Meme]:
    prefix, start_page, suffix = _parse_paged_url(base_url)

    all_new_memes: List[Meme] = []
    fetched_pages = 0
    stop_id: Optional[str] = None
    stop_page: Optional[int] = None

    logger.info("Starting scrape: base_url=%s start_page=%s max_pages=%s known_ids=%s",base_url,start_page,max_pages,len(known_ids))

    playwright, browser, context, page = make_browser()
    try:
        for page_number in range(start_page, start_page + max_pages):
            page_url = f"{prefix}{page_number}{suffix}"
            html = fetch_html(page, page_url)
            soup = BeautifulSoup(html, "html.parser")
            page_memes = scrape_memes(soup)
            fetched_pages += 1

            logger.info("Scanned page=%s url=%s memes_found=%s",page_number,page_url,len(page_memes))
            if not page_memes:
                logger.warning("No memes found on page=%s. Stopping pagination.", page_number)
                break

            for meme in page_memes:
                meme_id = str(meme.id)

                if meme_id and meme_id in known_ids:
                    stop_id = meme_id
                    stop_page = page_number
                    logger.info("Stopping on known meme id=%s at page=%s after fetched_pages=%s.",stop_id,stop_page,fetched_pages)
                    return all_new_memes

                all_new_memes.append(meme)

            if delay_seconds > 0:
                time.sleep(delay_seconds)
    finally:
        context.close()
        browser.close()
        playwright.stop()

    logger.info("Finished scraping without known-id stop. fetched_pages=%s new_memes=%s last_stop_id=%s last_stop_page=%s",fetched_pages,len(all_new_memes),stop_id,stop_page)
    return all_new_memes