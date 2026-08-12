"""Draft-pick ownership from a local RealGM future-drafts snapshot.

`nba_api` publishes no pick ownership, so — exactly like contracts — this is an optional
secondary dataset the operator downloads themselves. The file stays on the machine that
fetched it (`data/imports/` is gitignored in full); only normalized, attributable rows
reach the database.

## What the source actually contains, measured

The snapshot is "NBA Future Draft Pick Details": 30 team sections, each listing the picks
that team has traded away or acquired. It is **not** a full ownership table — a pick that
has never been traded appears nowhere, and is owned by its original team by default.

Parsed from the 2026-07-28 snapshot: **394 entries** (195 outgoing, each traded pick
appearing once from each side). Classified by how they convey:

    unconditional   184   a named team's pick, to a named team, no conditions
    swap            161   "the more favourable of", "the less favourable of"
    protected        33   "protected for selections 1-4"
    conditional      16   "if X conveys a 1st to Y, then ...", "Y may convey this pick"
    unparsed          0

That import yields **92 verified picks and 103 unresolved entries**, with zero unmatched
team names.

**Only the unconditional half becomes verified ownership.** The rest is recorded with its
source sentence intact, `is_verified = False`, and a `conveyance` class — because a swap's
outcome depends on two teams' finishes, and a protected pick may not convey at all. There
is no honest way to write "Charlotte owns this" for either.

## What that means downstream

A team's ownership of its own pick in a given year is treated as **verified** only if no
entry — conditional or not — sends that pick anywhere. One unresolved swap involving a
team's 2029 first is enough for the Stepien rule to report `unavailable` for that team and
name the entry, which is the correct answer: the rule cannot be certified against an
ownership picture that is genuinely uncertain.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.core.logging import get_logger
from app.db.models import DataQualityIssue, DraftPick, Team
from app.ingestion.runs import sync_run

logger = get_logger(__name__)

SOURCE_PROVIDER = "realgm_future_drafts"
DEFAULT_SNAPSHOT = "data/imports/draft_picks/realgm_future_drafts.html"
UNRESOLVED_CHECK = "draft_pick_unresolved_conveyance"
UNMATCHED_TEAM_CHECK = "draft_pick_unmatched_team"

_SECTION_RE = re.compile(
    r"<h2>(?P<team>.*?) Future Traded Pick Details</h2>\s*(?P<table><table.*?</table>)", re.S
)
_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r'<td[^>]*data-th="(\w+)"[^>]*>(.*?)</td>', re.S)
_PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
_HEADLINE_RE = re.compile(r"\s*<strong>(.*?)</strong>\s*<br>\s*(.*)", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_HISTORY_RE = re.compile(r"\[[^\]]*\]")

# "Atlanta's 2027 1st round pick to San Antonio", optionally "(via Golden State)" or
# "(via Boston to Memphis)". Anchored end to end: anything with extra clauses is not
# unconditional, and must not match.
_UNCONDITIONAL_RE = re.compile(
    r"^(?P<original>[A-Za-z.'\- ]+?)'s? (?P<year>\d{4}) (?P<round>1st|2nd) round pick "
    # The routing history — "(via Golden State)", "(via Boston to Memphis)", and the
    # doubled "(via Atlanta; via Atlanta)" the source emits for a pick that changed hands
    # twice — says who it passed through, not whether it conveys. It does not make the
    # entry conditional.
    r"to (?P<owner>[A-Za-z.'\- ]+?)"
    r"(?: \(via [A-Za-z.'\- ]+(?: to [A-Za-z.'\- ]+)*"
    r"(?:; via [A-Za-z.'\- ]+(?: to [A-Za-z.'\- ]+)*)*\))?\.?$"
)

_SWAP_RE = re.compile(r"favorable|favourable|\bswap\b", re.IGNORECASE)
_PROTECTED_RE = re.compile(r"\bprotect", re.IGNORECASE)
# "may convey" is a condition even though the sentence contains no "if": the source uses
# it for a pick whose destination depends on a later election by the receiving team.
_CONDITIONAL_RE = re.compile(
    r"\bif\b|\bconditional\b|\bdeferred\b|\bmay convey\b", re.IGNORECASE
)

#: RealGM's short team names. Explicit, because the two Los Angeles franchises and the
#: multi-word cities are exactly where a fuzzy match silently assigns a pick to the wrong
#: team. A name absent here is reported as unmatched — never guessed.
TEAM_ALIASES: dict[str, str] = {
    "atlanta": "ATL",
    "boston": "BOS",
    "brooklyn": "BKN",
    "charlotte": "CHA",
    "chicago": "CHI",
    "cleveland": "CLE",
    "dallas": "DAL",
    "denver": "DEN",
    "detroit": "DET",
    "golden state": "GSW",
    "houston": "HOU",
    "indiana": "IND",
    "l.a. clippers": "LAC",
    "la clippers": "LAC",
    "los angeles clippers": "LAC",
    "l.a. lakers": "LAL",
    "la lakers": "LAL",
    "los angeles lakers": "LAL",
    "memphis": "MEM",
    "miami": "MIA",
    "milwaukee": "MIL",
    "minnesota": "MIN",
    "new orleans": "NOP",
    "new york": "NYK",
    "oklahoma city": "OKC",
    "orlando": "ORL",
    "philadelphia": "PHI",
    "phoenix": "PHX",
    "portland": "POR",
    "sacramento": "SAC",
    "san antonio": "SAS",
    "toronto": "TOR",
    "utah": "UTA",
    "washington": "WAS",
}


@dataclass(frozen=True)
class ParsedPick:
    """One traded-pick entry as the source states it."""

    original_team: str | None
    owning_team: str | None
    draft_year: int
    round_number: int
    conveyance: str
    protections: str | None
    source_text: str
    page_team: str
    side: str

    @property
    def is_unconditional(self) -> bool:
        return self.conveyance == "unconditional"


def snapshot_path(override: str | None = None) -> Path:
    if override:
        candidate = Path(override)
        return candidate if candidate.is_absolute() else BACKEND_DIR.parent / candidate
    return BACKEND_DIR.parent / DEFAULT_SNAPSHOT


def _text(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment)).strip()


def _classify(core: str) -> str:
    if _SWAP_RE.search(core):
        return "swap"
    if _PROTECTED_RE.search(core):
        return "protected"
    if _CONDITIONAL_RE.search(core):
        return "conditional"
    return "unparsed"


def parse_snapshot(markup: str) -> list[ParsedPick]:
    """Every traded-pick entry in the snapshot, classified by how it conveys.

    Both sides of each trade are returned. Deduplication happens at import time against
    the *outgoing* side, because that is the side whose sentence names the original team.
    """
    picks: list[ParsedPick] = []
    for section in _SECTION_RE.finditer(markup):
        page_team = section.group("team")
        for row in _ROW_RE.finditer(section.group("table")):
            cells = dict(_CELL_RE.findall(row.group(1)))
            for side in ("Incoming", "Outgoing"):
                for para in _PARA_RE.findall(cells.get(side, "")):
                    matched = _HEADLINE_RE.match(para)
                    if not matched:
                        continue
                    body = _text(matched.group(2))
                    core = _HISTORY_RE.sub("", body).strip()
                    unconditional = _UNCONDITIONAL_RE.match(core)
                    if unconditional and not (
                        _SWAP_RE.search(core)
                        or _PROTECTED_RE.search(core)
                        or _CONDITIONAL_RE.search(core)
                    ):
                        picks.append(
                            ParsedPick(
                                original_team=unconditional.group("original").strip(),
                                owning_team=unconditional.group("owner").strip(),
                                draft_year=int(unconditional.group("year")),
                                round_number=1 if unconditional.group("round") == "1st" else 2,
                                conveyance="unconditional",
                                protections=None,
                                source_text=body,
                                page_team=page_team,
                                side=side,
                            )
                        )
                        continue
                    year = re.search(r"\b(20\d{2})\b", _text(matched.group(1)))
                    headline = _text(matched.group(1))
                    picks.append(
                        ParsedPick(
                            original_team=None,
                            owning_team=None,
                            draft_year=int(year.group(1)) if year else 0,
                            round_number=1 if "first round" in headline.lower() else 2,
                            conveyance=_classify(core),
                            protections=core or None,
                            source_text=body,
                            page_team=page_team,
                            side=side,
                        )
                    )
    return picks


def resolve_team(name: str | None, by_abbr: dict[str, Team]) -> Team | None:
    if not name:
        return None
    abbr = TEAM_ALIASES.get(name.strip().lower())
    return by_abbr.get(abbr) if abbr else None


def import_draft_picks(db: Session, source: str | None = None) -> dict:
    """Replace the RealGM-sourced pick rows with the current snapshot's.

    Rows from other providers are untouched. Idempotent: a re-import of the same file
    produces the same rows.
    """
    path = snapshot_path(source)
    if not path.is_file():
        return {
            "error": f"no draft-pick snapshot at {path}",
            "hint": (
                "save https://basketball.realgm.com/nba/draft/future_drafts/ to "
                f"{DEFAULT_SNAPSHOT} (the file is gitignored and never redistributed)"
            ),
            "imported": 0,
        }

    markup = path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_snapshot(markup)
    retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    summary: dict[str, Any] = {
        "source_file": str(path),
        "source_retrieved_at": retrieved_at.isoformat(),
        "entries_parsed": len(parsed),
        "verified": 0,
        "unresolved": 0,
        "unmatched_team_names": 0,
        "by_conveyance": {},
    }

    with sync_run(db, "import_draft_picks") as run:
        now = datetime.now(UTC)
        by_abbr = {t.abbreviation.upper(): t for t in db.scalars(select(Team)).all()}
        for existing in db.scalars(
            select(DraftPick).where(DraftPick.source_provider == SOURCE_PROVIDER)
        ).all():
            db.delete(existing)
        for issue in db.scalars(
            select(DataQualityIssue).where(
                DataQualityIssue.check_name.in_((UNRESOLVED_CHECK, UNMATCHED_TEAM_CHECK)),
                DataQualityIssue.resolved_at.is_(None),
            )
        ).all():
            issue.resolved_at = now
        db.flush()

        counts: dict[str, int] = {}
        seen: set[tuple[str, int, int, str]] = set()
        for entry in parsed:
            counts[entry.conveyance] = counts.get(entry.conveyance, 0) + 1
            if entry.side != "Outgoing":
                # Each traded pick is listed by both teams; the outgoing sentence is the
                # one that names the original team, so it is the canonical row.
                continue
            if entry.is_unconditional:
                original = resolve_team(entry.original_team, by_abbr)
                owner = resolve_team(entry.owning_team, by_abbr)
                if original is None or owner is None:
                    summary["unmatched_team_names"] += 1
                    unknown = entry.original_team if original is None else entry.owning_team
                    db.add(
                        DataQualityIssue(
                            check_name=UNMATCHED_TEAM_CHECK,
                            severity="warning",
                            message=(
                                f"draft-pick entry names a team this importer cannot "
                                f"resolve ({unknown!r}); the pick was NOT imported: "
                                f"{entry.source_text[:200]}"
                            ),
                            entity=entry.page_team,
                        )
                    )
                    continue
                key = (original.id, entry.draft_year, entry.round_number, owner.id)
                if key in seen:
                    continue
                seen.add(key)
                db.add(
                    DraftPick(
                        original_team_id=original.id,
                        owning_team_id=owner.id,
                        draft_year=entry.draft_year,
                        round_number=entry.round_number,
                        protections=None,
                        is_verified=True,
                        conveyance="unconditional",
                        source_text=entry.source_text,
                        source_provider=SOURCE_PROVIDER,
                        source_record_id=f"{entry.page_team}|{entry.draft_year}|{entry.side}",
                        source_retrieved_at=retrieved_at,
                        ingestion_run_id=run.id,
                    )
                )
                summary["verified"] += 1
                run.rows_written += 1
                continue

            page = resolve_team(entry.page_team.rsplit(" ", 1)[0], by_abbr) or _team_by_full_name(
                entry.page_team, by_abbr
            )
            if page is None:
                summary["unmatched_team_names"] += 1
                continue
            db.add(
                DraftPick(
                    original_team_id=page.id,
                    owning_team_id=page.id,
                    draft_year=entry.draft_year,
                    round_number=entry.round_number,
                    protections=entry.protections,
                    is_verified=False,
                    conveyance=entry.conveyance,
                    source_text=entry.source_text,
                    source_provider=SOURCE_PROVIDER,
                    source_record_id=f"{entry.page_team}|{entry.draft_year}|{entry.side}",
                    source_retrieved_at=retrieved_at,
                    ingestion_run_id=run.id,
                )
            )
            db.add(
                DataQualityIssue(
                    check_name=UNRESOLVED_CHECK,
                    severity="warning",
                    message=(
                        f"{entry.page_team} {entry.draft_year} round {entry.round_number}: "
                        f"{entry.conveyance} conveyance, not reducible to an owner — "
                        f"{entry.source_text[:300]}"
                    ),
                    entity=entry.page_team,
                )
            )
            summary["unresolved"] += 1
            run.rows_written += 1

        summary["by_conveyance"] = counts
        run.detail = dict(summary)
        db.commit()

    logger.info(
        "import_draft_picks: %s entries parsed, %s unconditional picks verified, "
        "%s unresolved (%s)",
        summary["entries_parsed"],
        summary["verified"],
        summary["unresolved"],
        counts,
    )
    return summary


def _team_by_full_name(name: str, by_abbr: dict[str, Team]) -> Team | None:
    for team in by_abbr.values():
        if team.full_name.lower() == name.strip().lower():
            return team
    return None


def ownership_summary(db: Session, draft_year: int, round_number: int = 1) -> dict:
    """Who verifiably controls each team's own pick for a year, and who does not.

    A team's own pick counts as **retained and verified** only when no entry — resolved or
    not — moves it. That is deliberately strict: one unresolved swap is enough to make the
    answer unknown, and an unknown answer is the correct one.
    """
    teams = {t.id: t for t in db.scalars(select(Team)).all()}
    rows = db.scalars(
        select(DraftPick).where(
            DraftPick.draft_year == draft_year, DraftPick.round_number == round_number
        )
    ).all()
    conveyed_away: dict[str, list[DraftPick]] = {}
    unresolved: dict[str, list[DraftPick]] = {}
    acquired: dict[str, list[DraftPick]] = {}
    for row in rows:
        if row.is_verified:
            conveyed_away.setdefault(row.original_team_id, []).append(row)
            acquired.setdefault(row.owning_team_id, []).append(row)
        else:
            unresolved.setdefault(row.original_team_id, []).append(row)
    return {
        "draft_year": draft_year,
        "round_number": round_number,
        "teams": {
            team.abbreviation: {
                "own_pick_retained": team_id not in conveyed_away and team_id not in unresolved,
                "own_pick_conveyed_to": [
                    teams[p.owning_team_id].abbreviation for p in conveyed_away.get(team_id, [])
                ],
                "unresolved_entries": [
                    {"conveyance": p.conveyance, "source_text": p.source_text}
                    for p in unresolved.get(team_id, [])
                ],
                "acquired_picks": len(acquired.get(team_id, [])),
                "verified": team_id not in unresolved,
            }
            for team_id, team in teams.items()
        },
    }
