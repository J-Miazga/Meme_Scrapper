from __future__ import annotations
import json
import logging
import time
from typing import Iterable, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from models import (
    DISCORD_CONTENT_LIMIT,
    DISCORD_EMBED_LIMIT,
    MAX_RETRIES_PER_MESSAGE,
    REQUEST_TIMEOUT_SECONDS,
    SEND_DELAY_SECONDS,
    USER_AGENT,
    Meme,
)

logger = logging.getLogger(__name__)


def _build_message_content_and_embeds(meme: Meme) -> Tuple[List[str], List[dict]]:
    lines: List[str] = ["🧩 MEM"]
    embeds: List[dict] = []

    ordered_content = meme.ordered_content
    if not ordered_content:
        return [], []

    for item in ordered_content:
        item_type = str(item.get("type", "")).strip().lower()
        value = item.get("value")
        if not item_type or not value:
            continue

        value_str = str(value)
        if item_type == "text":
            lines.append(value_str)
        elif item_type == "image":
            embeds.append({"image": {"url": value_str}})
        elif item_type == "video":
            lines.append(value_str)

    logger.debug("Built Discord payload parts for meme id=%s: content_lines=%s embeds=%s", meme.id,len(lines),len(embeds))
    return lines, embeds


def _post_message(webhook_url: str, content: str, embeds: List[dict]) -> None:
    payload = {
        "content": content,
        "embeds": embeds[:DISCORD_EMBED_LIMIT],
        "allowed_mentions": {"parse": []},
    }
    logger.debug("Posting Discord webhook message: content_length=%s embeds=%s",len(content),len(payload["embeds"]))
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Discord webhook failed with status {resp.status}")
        logger.debug("Discord webhook message posted successfully with status=%s", resp.status)


def _safe_float(value: object) -> float | None:
    try:
        result = float(str(value).strip())
        if result > 0:
            return result
    except (TypeError, ValueError):
        return None
    return None


def _normalize_retry_delay(value: object) -> float | None:
    delay = _safe_float(value)
    if delay is None:
        return None
    if delay >= 120:
        delay = delay / 1000.0
    return delay


def _retry_after_seconds(headers: dict, error_body: str) -> float:
    reset_after = _normalize_retry_delay(headers.get("X-RateLimit-Reset-After"))
    if reset_after is not None:
        return reset_after

    if error_body:
        try:
            parsed = json.loads(error_body)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            body_delay = _normalize_retry_delay(parsed.get("retry_after"))
            if body_delay is not None:
                return body_delay

    retry_after = _normalize_retry_delay(headers.get("Retry-After"))
    if retry_after is not None:
        return retry_after

    return SEND_DELAY_SECONDS


def _send_message_with_retry(
    webhook_url: str,
    content: str,
    embeds: List[dict],
    meme: Meme,
) -> Tuple[bool, int]:
    rate_limit_retries = 0
    meme_id = meme.id

    for attempt in range(1, MAX_RETRIES_PER_MESSAGE + 1):
        try:
            _post_message(webhook_url, content, embeds)
            return True, rate_limit_retries
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429:
                rate_limit_retries += 1
                if attempt >= MAX_RETRIES_PER_MESSAGE:
                    logger.error("Skipping meme id=%s after %s attempts due to repeated 429 responses.",meme_id,attempt)
                    return False, rate_limit_retries

                wait_seconds = _retry_after_seconds(exc.headers, error_body)
                logger.warning("429 for meme id=%s on attempt %s. Retrying in %.2fs.",meme_id,attempt,wait_seconds)
                time.sleep(wait_seconds)
                continue

            logger.error("Skipping meme id=%s due to HTTP %s. Response: %s",meme_id,exc.code,error_body[:500])
            return False, rate_limit_retries
        except URLError as exc:
            if attempt >= MAX_RETRIES_PER_MESSAGE:
                logger.error("Skipping meme id=%s after %s attempts due to network error: %s",meme_id,attempt,exc)
                return False, rate_limit_retries
            logger.warning("Network error for meme id=%s on attempt %s: %s. Retrying in %.2fs.", meme_id, attempt, exc, SEND_DELAY_SECONDS)
            time.sleep(SEND_DELAY_SECONDS)
        except TimeoutError as exc:
            if attempt >= MAX_RETRIES_PER_MESSAGE:
                logger.error("Skipping meme id=%s after %s attempts due to timeout: %s", meme_id, attempt, exc)
                return False, rate_limit_retries
            logger.warning("Timeout for meme id=%s on attempt %s: %s. Retrying in %.2fs.", meme_id, attempt, exc, SEND_DELAY_SECONDS)
            time.sleep(SEND_DELAY_SECONDS)



def publish_memes(memes: Iterable[Meme], webhook_url: str) -> dict[str, int]:
    memes_list = list(memes)
    logger.info("Starting Discord publish step for %s meme(s).", len(memes_list))

    sent_count = 0
    skipped_empty = 0
    skipped_too_long = 0
    failed_send = 0
    total_rate_limit_retries = 0

    for meme in reversed(memes_list):
        lines, embeds = _build_message_content_and_embeds(meme)
        content = "\n".join(lines).strip()
        if not content:
            skipped_empty += 1
            continue
        if len(content) > DISCORD_CONTENT_LIMIT:
            skipped_too_long += 1
            logger.warning("Skipping meme id=%s because content length %s exceeds Discord limit %s.", meme.id, len(content), DISCORD_CONTENT_LIMIT)
            continue
        sent, rate_limit_retries = _send_message_with_retry(webhook_url, content, embeds, meme)
        total_rate_limit_retries += rate_limit_retries
        if not sent:
            failed_send += 1
            continue
        sent_count += 1
        logger.info("Successfully sent meme id=%s (%s/%s).", meme.id, sent_count, len(memes_list))
        time.sleep(SEND_DELAY_SECONDS)
        

    summary = {
        "sent_count": sent_count,
        "skipped_empty": skipped_empty,
        "skipped_too_long": skipped_too_long,
        "failed_send": failed_send,
        "total_rate_limit_retries": total_rate_limit_retries,
    }
    logger.info(
        "Discord publish finished. sent=%s skipped_empty=%s skipped_too_long=%s failed_send=%s retries_429=%s",
        summary["sent_count"],
        summary["skipped_empty"],
        summary["skipped_too_long"],
        summary["failed_send"],
        summary["total_rate_limit_retries"],
    )
    return summary