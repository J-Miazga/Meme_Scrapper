from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, List, Optional, Tuple
from urllib.request import Request, urlopen

import dotenv


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

DISCORD_WEBHOOK_URL = dotenv.get_key(".env", "DISCORD_WEBHOOK_URL")


def _build_message_content_and_embeds(meme: dict, include: List[str]) -> Tuple[List[str], List[dict]]:
    lines: List[str] = ["🧩 MEM"]
    embeds: List[dict] = []

    texts = meme.get("texts") or []
    images = meme.get("images") or []
    videos = meme.get("videos") or []

    order = meme.get("types") or []
    order = [str(item).lower() for item in order if str(item).strip()]
    if not order:
        order = ["image", "video", "text"]

    for item in order:
        if item == "text" and "text" in include:
            for text in texts:
                if text:
                    lines.append(str(text))
        elif item == "image" and "image" in include:
            for url in images:
                if url:
                    embeds.append({"image": {"url": str(url)}})
        elif item == "video" and "video" in include:
            for url in videos:
                if url:
                    lines.append(str(url))

    return lines, embeds


def _post_message(webhook_url: str, content: str, embeds: List[dict]) -> None:
    payload = {
        "content": content,
        "embeds": embeds[:10],
        "allowed_mentions": {"parse": []},
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(req) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Discord webhook failed with status {resp.status}")


def _iter_memes(data: dict) -> Iterable[dict]:
    memes = data.get("memes")
    if not isinstance(memes, list):
        return []
    return memes


def _normalize_include(value: str) -> List[str]:
    raw = [item.strip().lower() for item in value.split(",") if item.strip()]
    allowed = {"text", "image", "video"}
    include = [item for item in raw if item in allowed]
    return include or ["text", "image", "video"]


def _filter_memes(memes: Iterable[dict], meme_id: Optional[str], index: Optional[int]) -> List[dict]:
    def is_known(meme: dict) -> bool:
        return str(meme.get("combination", "unknown")).lower() != "unknown"

    if meme_id:
        return [m for m in memes if str(m.get("id")) == str(meme_id) and is_known(m)]
    if index is not None:
        memes_list = [m for m in memes if is_known(m)]
        if index < 0 or index >= len(memes_list):
            return []
        return [memes_list[index]]
    return [m for m in memes if is_known(m)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Send meme data to Discord via webhook.")
    parser.add_argument(
        "--json",
        default="images_1.json",
        help="Input JSON filename (default: images_1.json)",
    )
    parser.add_argument(
        "--webhook",
        default=DISCORD_WEBHOOK_URL,
        help="Discord webhook URL (default: DISCORD_WEBHOOK_URL from .env)",
    )
    parser.add_argument(
        "--include",
        default="text,image,video",
        help="Comma-separated keys to include: text,image,video (default: all)",
    )
    parser.add_argument(
        "--id",
        dest="meme_id",
        help="Send only a specific meme id",
    )
    parser.add_argument(
        "--index",
        type=int,
        help="Send only the meme at this index (0-based)",
    )
    args = parser.parse_args()

    if not args.webhook:
        print("Missing Discord webhook URL. Set DISCORD_WEBHOOK_URL in .env or pass --webhook.", file=sys.stderr)
        return 1

    try:
        with open(args.json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"JSON file not found: {args.json}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {args.json}: {exc}", file=sys.stderr)
        return 1

    include = _normalize_include(args.include)
    memes = _filter_memes(_iter_memes(data), args.meme_id, args.index)
    if not memes:
        print("No memes matched the provided filters.", file=sys.stderr)
        return 1

    for meme in memes:
        lines, embeds = _build_message_content_and_embeds(meme, include)
        content = "\n".join(lines).strip()
        if not content:
            continue
        if len(content) > 2000:
            content = content[:1990] + "\n[truncated]"
        _post_message(args.webhook, content, embeds)

    print(f"Sent {len(memes)} meme message(s) to Discord.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
