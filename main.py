from __future__ import annotations
import json
import logging
import os
import sys
from dotenv import load_dotenv
from discord_publisher import publish_memes
from scraper import scrape_until_known
from models import (
    DEFAULT_MAX_PAGES,
    DEFAULT_SCRAPE_DELAY_SECONDS,
    DISCORD_WEBHOOK_URL_ENV_VAR,
    LAST_SESSION_MEME_IDS,
    WEBSITE_URL_ENV_VAR,
)


def _configure_logging() -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("pipeline")


def _normalize_id(value: object) -> str:
    return str(value).strip()


def _known_ids_from_env(logger: logging.Logger) -> set[str]:
    raw = os.getenv("KNOWN_MEME_IDS")
    if not raw:
        fallback = {_normalize_id(item) for item in LAST_SESSION_MEME_IDS if _normalize_id(item)}
        logger.info("KNOWN_MEME_IDS not set. Using fallback ids from code (%s ids).", len(fallback))
        return fallback

    parsed: list[str] = []
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, list):
            parsed = [_normalize_id(item) for item in decoded if _normalize_id(item)]
        else:
            parsed = [_normalize_id(item) for item in raw.split(",") if _normalize_id(item)]
    except json.JSONDecodeError:
        parsed = [_normalize_id(item) for item in raw.split(",") if _normalize_id(item)]

    known_ids = set(parsed)
    logger.info("Loaded %s known id(s) from KNOWN_MEME_IDS.", len(known_ids))
    return known_ids


def main() -> int:
    load_dotenv()
    logger = _configure_logging()

    website_url = os.getenv(WEBSITE_URL_ENV_VAR)
    webhook_url = os.getenv(DISCORD_WEBHOOK_URL_ENV_VAR)
    if not website_url:
        logger.error("Missing required environment variable: %s", WEBSITE_URL_ENV_VAR)
        return 1
    if not webhook_url:
        logger.error("Missing required environment variable: %s", DISCORD_WEBHOOK_URL_ENV_VAR)
        return 1

    delay_seconds = DEFAULT_SCRAPE_DELAY_SECONDS
    max_pages = DEFAULT_MAX_PAGES
    known_ids = _known_ids_from_env(logger)

    logger.info("Pipeline started. url=%s max_pages=%s delay_seconds=%s",website_url,max_pages, delay_seconds)

    try:
        memes = scrape_until_known(
            base_url=website_url,
            delay_seconds=delay_seconds,
            known_ids=known_ids,
            max_pages=max_pages,
        )
    except Exception:
        logger.exception("Scraping step failed.")
        return 1

    logger.info("Scraping step finished. New memes=%s", len(memes))
    if not memes:
        logger.info("Pipeline finished successfully. Nothing to publish.")
        return 0

    try:
        summary = publish_memes(memes=memes, webhook_url=webhook_url)
    except Exception:
        logger.exception("Publishing step failed.")
        return 1

    logger.info("Pipeline finished successfully.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
