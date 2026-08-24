"""Parse Basketball-Reference season transaction pages into normalized trade records.

Pure functions over markup: no database, no network, no identity resolution. Everything
here is testable against a fixture string, and the importer is the only thing that decides
what a parsed name means.

## The shape of the source

Each season page is a `<ul>` of `<li><span>DATE</span><p>…</p><p>…</p></li>` — one `<li>`
per date, one `<p>` per transaction. A trade paragraph takes one of two forms:

    The <A> traded X, Y and a 2032 2nd round draft pick to the <B> for Z.  <notes>
    In a 3-team trade, the <A> traded X to the <B>; the <B> traded …; and  the <C> …  <notes>

Team anchors carry `data-attr-from` / `data-attr-to` with the three-letter abbreviation,
which is what makes multi-team legs unambiguous: a team that both sends and receives
appears as two anchors with two different attributes, so direction never has to be
inferred from word order.

## Two things the parser refuses to do

**A player link inside a pick description is not a traded player.** BBRef annotates a
conveyed pick with who it became — `a 2026 2nd round draft pick (<a>Jack Kayil</a> was
later selected)`. Counting those anchors as players inflates the 2025-26 page from 128
real player legs to 184 anchors, and it would put a rookie on the wrong side of a trade
that happened before he was drafted. The annotation is captured as `later_selected`
metadata on the pick instead.

**An asset phrase the grammar does not recognize is kept verbatim, not dropped.** Every
item that fails to match a known form lands in `unparsed_assets` and the importer files it
as a data-quality warning. A trade with an unparsed asset is still a real trade; silently
losing a leg of it is how a comparable-trade engine ends up comparing against a deal that
never happened.

## Conveyance

The trailing notes carry the pick conditions in the source's own words — "2031 1st-rd pick
is a swap", "2026 2nd-rd pick was MEM own (protected 43-60) and conveyed", "conditional
2028 2nd-rd pick is DEN own". Notes are bound to picks by (year, round). Where a trade
moves two picks with the same year and round the binding is genuinely ambiguous, so the
note is attached to **both** and flagged rather than assigned to one of them.

The conveyance vocabulary is the one `draft_picks.conveyance` already uses —
`unconditional | protected | swap | conditional | unparsed` — so a reader who has seen one
does not have to learn another.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime

_LI_RE = re.compile(r"<li><span>(?P<date>[^<]*)</span>(?P<body>.*?)</li>", re.S)
_P_RE = re.compile(r"<p>(?P<body>.*?)</p>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

_TEAM_FROM_RE = re.compile(r'<a\s+data-attr-from="(?P<abbr>[A-Z]{3})"[^>]*>(?P<name>.*?)</a>', re.S)
_TEAM_TO_RE = re.compile(r'<a\s+data-attr-to="(?P<abbr>[A-Z]{3})"[^>]*>(?P<name>.*?)</a>', re.S)
_PLAYER_RE = re.compile(
    r'<a\s+href="/players/\w/(?P<slug>[a-z0-9]+)\.html"[^>]*>(?P<name>.*?)</a>', re.S
)

#: Markers substituted for anchors before the sentence is flattened to text. The guillemet
#: pair does not occur in the source, so a marker can never collide with prose.
_FROM_MARK = "«FROM:{abbr}»"
_TO_MARK = "«TO:{abbr}»"
_PLAYER_MARK = "«P:{slug}:{name}»"

_MARK_RE = re.compile(r"«(?P<kind>FROM|TO|P):(?P<payload>[^»]*)»")
_PLAYER_MARK_RE = re.compile(r"«P:(?P<slug>[a-z0-9]+):(?P<name>[^»]*)»")

_MULTI_TEAM_RE = re.compile(r"^In a (?P<n>\d+)-team trade,\s*", re.I)
_LEG_RE = re.compile(
    r"[Tt]he «FROM:(?P<from>[A-Z]{3})»\s+traded\s+(?P<assets>.*?)"
    r"\s*to the «TO:(?P<to>[A-Z]{3})»",
    re.S,
)
#: The two-team form's return package: everything after the receiving team, up to the
#: sentence's terminal period.
_FOR_RE = re.compile(r"«TO:(?P<to>[A-Z]{3})»\s+for\s+(?P<assets>.+?)\.?$", re.S)

#: The last receiving team in the sentence. Everything the transaction sentence still has
#: to say comes after it — in the two-team form, the `for` package; in the multi-team form,
#: nothing — so the sentence's terminal period is the first one at or after this marker.
_LAST_TO_RE = re.compile(r"«TO:[A-Z]{3}»")

_PICK_RE = re.compile(
    r"^(?:an?|the)\s+(?P<year>(?:19|20)\d{2})\s+(?P<round>1st|2nd)\s+round\s+draft\s+pick"
    r"(?:\s*\((?P<annotation>[^)]*)\))?$",
    re.I,
)
_DRAFT_RIGHTS_RE = re.compile(r"^the draft rights to\s+(?P<rest>.+)$", re.I)
#: `cash`, `cash considerations`, `$200K`, `$1.3M cash`. The amount is not retained:
#: it appears on a minority of legs and a partially-populated money column reads as a
#: measurement of trade size, which it is not.
_CASH_RE = re.compile(r"^(?:cash(?: considerations)?|\$[\d.,]+[KMB]?(?: cash)?)$", re.I)

_NOTE_PICK_RE = re.compile(
    r"(?P<year>(?:19|20)\d{2})\s+(?P<round>1st|2nd)-(?:rd|d)\s+pick", re.I
)
_SWAP_RE = re.compile(r"favorable|favourable|\bswap\b", re.I)
_PROTECTED_RE = re.compile(r"\bprotect", re.I)
_CONDITIONAL_RE = re.compile(r"\bif\b|\bconditional\b|\bdeferred\b|\bmay convey\b", re.I)
#: "Boston received a trade exception", "Los Angeles received trade exceptions". The city
#: run must be entirely capitalised words: a permissive character class swallows the
#: preceding note ("...rd pick is LAL own Los Angeles received a trade exception") and
#: reports a city that is not one. The city is left as the source wrote it — the importer
#: resolves it against the trade's own participants, and refuses when two of them share a
#: city, which is exactly the Los Angeles case.
_TRADE_EXCEPTION_RE = re.compile(
    r"(?P<city>[A-Z][a-zA-Z.']*(?:\s+[A-Z][a-zA-Z.']*)*)\s+received\b[^.]{0,40}?trade exception"
)

CONVEYANCE_CLASSES = ("unconditional", "protected", "swap", "conditional", "unparsed")


@dataclass(frozen=True)
class ParsedPlayer:
    """A player leg. `slug` is the Basketball-Reference player id, kept so a resolution
    can be re-checked against the source rather than only against a name."""

    slug: str
    name: str
    via_draft_rights: bool = False


@dataclass(frozen=True)
class ParsedPick:
    draft_year: int
    round_number: int
    conveyance: str = "unconditional"
    #: The source's own sentence about this pick, verbatim.
    note_text: str | None = None
    #: True when more than one pick in the trade shares this (year, round), so the note
    #: could not be bound to exactly one of them.
    note_binding_ambiguous: bool = False
    #: "(<player> was later selected)" — who the pick became. Never a traded player.
    later_selected: str | None = None


@dataclass(frozen=True)
class ParsedLeg:
    from_abbr: str
    to_abbr: str
    players: tuple[ParsedPlayer, ...] = ()
    picks: tuple[ParsedPick, ...] = ()
    cash: bool = False
    unparsed_assets: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedTrade:
    transaction_date: date
    season: str
    n_teams: int
    team_abbrs: tuple[str, ...]
    legs: tuple[ParsedLeg, ...] = ()
    notes_text: str = ""
    source_text: str = ""
    trade_exception_cities: tuple[str, ...] = ()
    unparsed_assets: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_multi_team(self) -> bool:
        return self.n_teams > 2


@dataclass
class ParseReport:
    """What the parse saw, so coverage is a measurement rather than an assumption."""

    paragraphs: int = 0
    trade_paragraphs: int = 0
    trades_parsed: int = 0
    trades_unparsed: list[str] = field(default_factory=list)
    multi_team: int = 0
    unparsed_assets: list[str] = field(default_factory=list)
    dates_unparsed: list[str] = field(default_factory=list)


def _text(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment)).strip()


def _markerize(fragment: str) -> str:
    """Replace anchors with collision-free markers, then flatten to text.

    Order matters: player anchors are substituted last so that a team anchor whose href
    happens to look like a player link cannot be captured as a player.
    """
    out = _TEAM_FROM_RE.sub(lambda m: _FROM_MARK.format(abbr=m.group("abbr")), fragment)
    out = _TEAM_TO_RE.sub(lambda m: _TO_MARK.format(abbr=m.group("abbr")), out)
    out = _PLAYER_RE.sub(
        lambda m: _PLAYER_MARK.format(slug=m.group("slug"), name=_text(m.group("name"))), out
    )
    out = html.unescape(_TAG_RE.sub("", out))
    # Newlines and tabs become single spaces; runs of ordinary spaces are LEFT ALONE,
    # because `.  ` is the source's separator between the transaction sentence and its
    # notes, and collapsing whitespace merges the two into one unreadable string.
    out = out.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return out.replace("\u00a0", " ").strip()


def _plain(marked: str) -> str:
    """Marked text back to readable prose, for `source_text`."""
    def _sub(match: re.Match[str]) -> str:
        payload = match.group("payload")
        if match.group("kind") == "P":
            return payload.split(":", 1)[1] if ":" in payload else payload
        return payload
    return _MARK_RE.sub(_sub, marked)


def split_sentence_and_notes(marked: str) -> tuple[str, str]:
    """Separate the transaction sentence from the trailing notes.

    The obvious rule — split on a period followed by two spaces — reads the 2022-23
    season onwards and **fails on everything before it**: the source used a single space
    until then. Applied to the ten-season corpus that rule left 214 asset phrases
    unparsed, all of them a real asset with a note glued to it, and it classified every
    pre-2022 pick as unconditional because the conditions were never seen as notes.

    The rule that works on both is structural rather than typographic. The sentence's last
    structural element is the final receiving team, so the sentence ends at the first
    period at or after that marker which is **outside a parenthesis and outside a marker**.
    Both shields are load-bearing: `A.J. Griffin` and `Vince Williams Jr.` put `. ` inside
    a name, and `(Tyrell Terry was later selected)` puts one inside an annotation.
    """
    matches = list(_LAST_TO_RE.finditer(marked))
    start = matches[-1].end() if matches else 0
    depth = 0
    in_marker = False
    i = start
    while i < len(marked):
        char = marked[i]
        if char == "«":
            in_marker = True
        elif char == "»":
            in_marker = False
        elif not in_marker:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == "." and depth == 0:
                tail = marked[i + 1 :]
                if not tail.strip():
                    return marked[: i + 1], ""
                if tail[:1].isspace():
                    return marked[: i + 1], tail.strip()
        i += 1
    return marked, ""


def _split_assets(chunk: str) -> list[str]:
    """`A, B and a 2027 2nd round draft pick` -> three items.

    Split on `, ` and ` and `, but not inside a marker or a parenthesis — the pick
    annotation `(X was later selected)` contains neither, and player markers cannot
    contain a comma because the source's own anchor text does not.
    """
    items: list[str] = []
    depth = 0
    buffer: list[str] = []
    i = 0
    while i < len(chunk):
        char = chunk[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if depth == 0:
            if char == "," and chunk[i : i + 2] == ", ":
                items.append("".join(buffer))
                buffer = []
                i += 2
                continue
            if chunk.startswith(" and ", i):
                items.append("".join(buffer))
                buffer = []
                i += 5
                continue
        buffer.append(char)
        i += 1
    items.append("".join(buffer))
    return [item.strip() for item in items if item.strip()]


def _parse_asset(item: str) -> tuple[str, object]:
    """Classify one asset phrase. Returns (kind, value); kind is player|pick|cash|unparsed."""
    if _CASH_RE.match(item):
        return "cash", True
    pick = _PICK_RE.match(item)
    if pick:
        annotation = pick.group("annotation")
        later = None
        if annotation:
            named = _PLAYER_MARK_RE.search(annotation)
            later = named.group("name") if named else _plain(annotation).strip()
        return "pick", ParsedPick(
            draft_year=int(pick.group("year")),
            round_number=1 if pick.group("round").lower() == "1st" else 2,
            later_selected=later,
        )
    rights = _DRAFT_RIGHTS_RE.match(item)
    target = rights.group("rest") if rights else item
    player = _PLAYER_MARK_RE.fullmatch(target.strip())
    if player:
        return "player", ParsedPlayer(
            slug=player.group("slug"), name=player.group("name"), via_draft_rights=bool(rights)
        )
    return "unparsed", _plain(item)


def _classify_note(note: str) -> str:
    if _SWAP_RE.search(note):
        return "swap"
    if _PROTECTED_RE.search(note):
        return "protected"
    if _CONDITIONAL_RE.search(note):
        return "conditional"
    return "unconditional"


#: A qualifier the source writes *before* the pick it qualifies — "conditional 2028 2nd-rd
#: pick is DEN own". Cutting the note at the year would leave the qualifier attached to the
#: previous note and classify the pick as unconditional, which is the one classification it
#: is not. Measured on the ten-season corpus, restoring these moves 34 pick legs out of
#: `unconditional`.
_QUALIFIER_RE = re.compile(r"(?:conditional|protected|unprotected)\s+$", re.I)


def _qualified_start(notes: str, start: int) -> int:
    """Move a note boundary back over a qualifier that belongs to the pick after it."""
    prefix = notes[:start]
    match = _QUALIFIER_RE.search(prefix)
    return match.start() if match else start


def _split_notes(notes: str) -> list[str]:
    """Notes arrive as one run-on string. Split before each `<year> <round>-rd pick`
    mention and before each trade-exception sentence, keeping the source's words."""
    if not notes:
        return []
    boundaries = [_qualified_start(notes, m.start()) for m in _NOTE_PICK_RE.finditer(notes)]
    boundaries += [m.start() for m in _TRADE_EXCEPTION_RE.finditer(notes)]
    cuts = sorted({0, *(b for b in boundaries if b > 0), len(notes)})
    pieces = []
    for start, end in zip(cuts[:-1], cuts[1:], strict=False):
        piece = notes[start:end].strip()
        if piece:
            pieces.append(piece)
    return pieces


def _bind_notes(legs: list[ParsedLeg], notes: str) -> list[ParsedLeg]:
    """Attach each pick note to the pick(s) it names, by (year, round)."""
    pieces = _split_notes(notes)
    by_key: dict[tuple[int, int], list[str]] = {}
    for piece in pieces:
        match = _NOTE_PICK_RE.search(piece)
        if not match:
            continue
        key = (int(match.group("year")), 1 if match.group("round").lower() == "1st" else 2)
        by_key.setdefault(key, []).append(piece)

    counts: dict[tuple[int, int], int] = {}
    for leg in legs:
        for pick in leg.picks:
            key = (pick.draft_year, pick.round_number)
            counts[key] = counts.get(key, 0) + 1

    rebuilt: list[ParsedLeg] = []
    for leg in legs:
        picks: list[ParsedPick] = []
        for pick in leg.picks:
            key = (pick.draft_year, pick.round_number)
            matched = by_key.get(key, [])
            note_text = " ".join(matched) if matched else None
            picks.append(
                ParsedPick(
                    draft_year=pick.draft_year,
                    round_number=pick.round_number,
                    conveyance=_classify_note(note_text) if note_text else "unconditional",
                    note_text=note_text,
                    note_binding_ambiguous=bool(matched) and counts.get(key, 0) > 1,
                    later_selected=pick.later_selected,
                )
            )
        rebuilt.append(
            ParsedLeg(
                from_abbr=leg.from_abbr,
                to_abbr=leg.to_abbr,
                players=leg.players,
                picks=tuple(picks),
                cash=leg.cash,
                unparsed_assets=leg.unparsed_assets,
            )
        )
    return rebuilt


def _build_leg(from_abbr: str, to_abbr: str, assets: str) -> ParsedLeg:
    players: list[ParsedPlayer] = []
    picks: list[ParsedPick] = []
    unparsed: list[str] = []
    cash = False
    for item in _split_assets(assets):
        kind, value = _parse_asset(item)
        if kind == "player":
            players.append(value)  # type: ignore[arg-type]
        elif kind == "pick":
            picks.append(value)  # type: ignore[arg-type]
        elif kind == "cash":
            cash = True
        else:
            unparsed.append(str(value))
    return ParsedLeg(
        from_abbr=from_abbr,
        to_abbr=to_abbr,
        players=tuple(players),
        picks=tuple(picks),
        cash=cash,
        unparsed_assets=tuple(unparsed),
    )


def parse_trade_paragraph(marked: str, when: date, season: str) -> ParsedTrade | None:
    """One flattened transaction sentence to a trade, or None if it is not a trade."""
    body, notes = split_sentence_and_notes(marked)

    multi = _MULTI_TEAM_RE.match(body)
    legs: list[ParsedLeg] = []
    if multi:
        sentence = _MULTI_TEAM_RE.sub("", body)
        for chunk in sentence.split(";"):
            chunk = re.sub(r"^\s*and\s+", "", chunk.strip())
            match = _LEG_RE.search(chunk)
            if match:
                legs.append(
                    _build_leg(match.group("from"), match.group("to"), match.group("assets"))
                )
    else:
        match = _LEG_RE.search(body)
        if not match:
            return None
        legs.append(_build_leg(match.group("from"), match.group("to"), match.group("assets")))
        back = _FOR_RE.search(body)
        if back:
            legs.append(
                _build_leg(back.group("to"), match.group("from"), back.group("assets"))
            )
    if not legs:
        return None

    legs = _bind_notes(legs, notes)
    abbrs: list[str] = []
    for leg in legs:
        for abbr in (leg.from_abbr, leg.to_abbr):
            if abbr not in abbrs:
                abbrs.append(abbr)
    declared = int(multi.group("n")) if multi else 2
    exceptions = tuple(m.group("city").strip() for m in _TRADE_EXCEPTION_RE.finditer(notes))
    return ParsedTrade(
        transaction_date=when,
        season=season,
        n_teams=max(declared, len(abbrs)),
        team_abbrs=tuple(sorted(abbrs)),
        legs=tuple(legs),
        notes_text=notes.strip(),
        source_text=_plain(marked).strip(),
        trade_exception_cities=exceptions,
        unparsed_assets=tuple(a for leg in legs for a in leg.unparsed_assets),
    )


def parse_season_page(markup: str, season: str) -> tuple[list[ParsedTrade], ParseReport]:
    """Every trade on one season page, with a report of what the parse could not read."""
    report = ParseReport()
    trades: list[ParsedTrade] = []
    for entry in _LI_RE.finditer(markup):
        raw_date = _text(entry.group("date"))
        try:
            when = datetime.strptime(raw_date, "%B %d, %Y").date()
        except ValueError:
            report.dates_unparsed.append(raw_date)
            continue
        for paragraph in _P_RE.finditer(entry.group("body")):
            report.paragraphs += 1
            fragment = paragraph.group("body")
            if " traded " not in fragment or "data-attr-from" not in fragment:
                continue
            report.trade_paragraphs += 1
            marked = _markerize(fragment)
            trade = parse_trade_paragraph(marked, when, season)
            if trade is None:
                report.trades_unparsed.append(_plain(marked)[:300])
                continue
            trades.append(trade)
            report.trades_parsed += 1
            if trade.is_multi_team:
                report.multi_team += 1
            report.unparsed_assets.extend(trade.unparsed_assets)
    return trades, report
