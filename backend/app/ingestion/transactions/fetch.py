"""Fetch Basketball-Reference season transaction pages into the local import drop-zone.

## Why a fetcher exists here at all

Every other secondary dataset in this repository is a page the operator saves by hand
(`data/imports/contracts/players.html`, `data/imports/draft_picks/...`). Transactions
need **ten** pages rather than one, and they are re-fetched whenever the season advances,
so saving them by hand is the wrong ergonomics for the same job.

The fetch is deliberately conservative, and the constraints are read from the source's own
published policy rather than assumed:

- `https://www.basketball-reference.com/robots.txt` allows `/leagues/` for `User-agent: *`
  and publishes `Crawl-delay: 3`. `REQUEST_INTERVAL_SECONDS` is 3.5 — the published delay
  plus margin — and it is enforced between *every* request, including retries.
- The same robots file **disallows** `*/on-off/` and `*/lineups/`. That is one of the two
  measurements behind R6's decision not to build a lineup-aware fit model; see
  `docs/limitations.md`.
- One request per season page, and nothing is followed. No player pages, no team pages,
  no crawl.
- The raw HTML lands in `data/imports/transactions/`, which is gitignored, and is never
  redistributed. A `provenance.json` sidecar records the URL, the HTTP status, the byte
  count, the SHA-256 of the body and the retrieval timestamp, so a parse can always be
  traced to the exact bytes it read.

Nothing here runs on a request path or on a schedule. It is an operator command:

    make fetch-transactions FROM=2017 TO=2026
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import BACKEND_DIR
from app.core.logging import get_logger

logger = get_logger(__name__)

SOURCE_PROVIDER = "bbref_transactions"
BASE_URL = "https://www.basketball-reference.com/leagues/NBA_{end_year}_transactions.html"
DEFAULT_DIR = "data/imports/transactions"
PROVENANCE_FILE = "provenance.json"

#: The source's published `Crawl-delay` is 3 seconds. This is that plus margin, applied
#: between every request including retries — never divided by a concurrency factor,
#: because there is no concurrency here.
REQUEST_INTERVAL_SECONDS = 3.5
REQUEST_TIMEOUT_SECONDS = 60.0
#: Identifies the client and gives a human a way to complain. A generic browser string
#: would misrepresent what is making the request.
USER_AGENT = (
    "RosterLab/0.6 (local research project; one request per season page; "
    "honours robots.txt Crawl-delay)"
)


class FetchRefused(RuntimeError):
    """Raised when a fetch cannot proceed under the terms this module commits to."""


@dataclass(frozen=True)
class FetchedPage:
    season: str
    end_year: int
    url: str
    path: str
    bytes: int
    sha256: str
    retrieved_at: str
    status: int


def season_label(end_year: int) -> str:
    """`2026` -> `2025-26`. Basketball-Reference names a season by its ending year."""
    return f"{end_year - 1}-{str(end_year)[-2:]}"


def transactions_dir(override: str | None = None) -> Path:
    if override:
        candidate = Path(override)
        return candidate if candidate.is_absolute() else BACKEND_DIR.parent / candidate
    return BACKEND_DIR.parent / DEFAULT_DIR


def _read_provenance(directory: Path) -> dict[str, dict]:
    path = directory / PROVENANCE_FILE
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded.get("pages", {}) if isinstance(loaded, dict) else {}


def _write_provenance(directory: Path, pages: dict[str, dict]) -> None:
    (directory / PROVENANCE_FILE).write_text(
        json.dumps(
            {
                "source_provider": SOURCE_PROVIDER,
                "source_name": "Basketball-Reference season transaction pages",
                "source_url_pattern": BASE_URL,
                "robots_crawl_delay_seconds": 3,
                "request_interval_seconds": REQUEST_INTERVAL_SECONDS,
                "user_agent": USER_AGENT,
                "redistribution": (
                    "raw pages are gitignored and never committed; only normalized, "
                    "attributable rows derived from them enter the database"
                ),
                "pages": pages,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _fetch_one(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        return int(exc.code), b""


def fetch_seasons(
    first_end_year: int,
    last_end_year: int,
    directory: str | None = None,
    force: bool = False,
) -> dict:
    """Fetch one page per season into the import drop-zone.

    Existing files are kept unless `force` is set: a season that has already been
    retrieved is not re-requested, so re-running the command after adding one season
    issues exactly one request.
    """
    if first_end_year > last_end_year:
        raise FetchRefused("first season must not be after last season")
    target = transactions_dir(directory)
    target.mkdir(parents=True, exist_ok=True)
    pages = _read_provenance(target)

    fetched: list[FetchedPage] = []
    skipped: list[str] = []
    failed: list[dict] = []
    requests_made = 0

    for end_year in range(first_end_year, last_end_year + 1):
        season = season_label(end_year)
        filename = f"NBA_{end_year}_transactions.html"
        path = target / filename
        if path.is_file() and not force:
            skipped.append(season)
            continue
        if requests_made:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        url = BASE_URL.format(end_year=end_year)
        status, body = _fetch_one(url)
        requests_made += 1
        if status != 200 or not body:
            failed.append({"season": season, "url": url, "status": status})
            logger.warning("transaction page fetch failed: %s (%s)", url, status)
            continue
        path.write_bytes(body)
        page = FetchedPage(
            season=season,
            end_year=end_year,
            url=url,
            path=filename,
            bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            retrieved_at=datetime.now(UTC).isoformat(),
            status=status,
        )
        pages[season] = asdict(page)
        fetched.append(page)

    _write_provenance(target, pages)
    return {
        "directory": str(target),
        "requested": [season_label(y) for y in range(first_end_year, last_end_year + 1)],
        "fetched": [asdict(p) for p in fetched],
        "skipped_already_present": skipped,
        "failed": failed,
        "requests_made": requests_made,
        "request_interval_seconds": REQUEST_INTERVAL_SECONDS,
    }
