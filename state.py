from __future__ import annotations
import json
import logging
import os
from models import CHECKPOINT_SIZE, Meme


def _normalize_id(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe_ids_preserve_order(items: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def known_ids_from_env(logger: logging.Logger) -> list[str]:
    raw = os.getenv("KNOWN_MEME_IDS")
    if raw is None or not raw.strip():
        raise ValueError("Missing required KNOWN_MEME_IDS. Set it as a JSON array string")

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("KNOWN_MEME_IDS must be valid JSON array string") from exc

    if not isinstance(decoded, list):
        raise ValueError("KNOWN_MEME_IDS must be a JSON array")

    parsed = [_normalize_id(item) for item in decoded if _normalize_id(item)]

    known_ids = _dedupe_ids_preserve_order(parsed)
    logger.info("Loaded %s known id(s) from KNOWN_MEME_IDS.", len(known_ids))
    return known_ids


def build_checkpoint_ids(memes: list[Meme], known_ids: list[str], size: int = CHECKPOINT_SIZE) -> list[str]:
    fresh_ids: list[str] = []
    for meme in memes:
        meme_id = _normalize_id(meme.id)
        if meme_id:
            fresh_ids.append(meme_id)
    merged = fresh_ids + known_ids
    return _dedupe_ids_preserve_order(merged)[:size]


def _set_github_output(name: str, value: str, logger: logging.Logger) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return

    with open(output_path, "a", encoding="utf-8") as output_file:
        output_file.write(f"{name}={value}\n")
    logger.info("Exported GitHub output: %s", name)


def export_checkpoint_output(memes: list[Meme], known_ids: list[str], logger: logging.Logger) -> None:
    checkpoint_ids = build_checkpoint_ids(memes=memes, known_ids=known_ids, size=CHECKPOINT_SIZE)
    _set_github_output(
        name="checkpoint_meme_ids",
        value=json.dumps(checkpoint_ids, separators=(",", ":")),
        logger=logger,
    )
