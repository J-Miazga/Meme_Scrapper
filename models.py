from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

WEBSITE_URL_ENV_VAR = "WEBSITE_URL"
DISCORD_WEBHOOK_URL_ENV_VAR = "DISCORD_WEBHOOK_URL"

CHECKPOINT_SIZE = 5
LAST_SESSION_MEME_IDS: List[int] = [
    4395405,
    4396095,
    4395942,
    4395674,
    4395452,
]

DEFAULT_FETCH_RETRIES = 3
DEFAULT_FETCH_SLEEP_SECONDS = 1.0
DEFAULT_SCRAPE_DELAY_SECONDS = 2.0
DEFAULT_MAX_PAGES = 20
DISCORD_CONTENT_LIMIT = 2000
DISCORD_EMBED_LIMIT = 10
SEND_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 15
MAX_RETRIES_PER_MESSAGE = 5
MAX_RETRY_WAIT_SECONDS = 60.0


@dataclass(slots=True)
class Meme:
    id: str | None = None
    combination: str = "unknown"
    ordered_content: List[Dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._refresh_combination()

    def _refresh_combination(self) -> None:
        has_any_type = any(
            str(item.get("type", "")).strip().lower()
            for item in self.ordered_content
            if isinstance(item, dict)
        )
        self.combination = "correct" if has_any_type else "unknown"