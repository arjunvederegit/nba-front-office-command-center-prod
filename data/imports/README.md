# data/imports/

Drop-zone for user-supplied import files (gitignored — nothing here is committed).

| File | Used by | Command |
| --- | --- | --- |
| `nba_player_stats_2026.csv` | 2025-26 season-totals import (Player Lab) | `make import-stats-csv` |
| `contracts/players.html` | Basketball-Reference contracts snapshot parser (Cap Lab, salary rules) | set `CONTRACT_DATA_PROVIDER=bbref_snapshot`, then `make sync-data` |
| `draft_picks/realgm_future_drafts.html` | Draft-pick ownership (Stepien rule, asset valuation) | `make import-draft-picks` |
| `transactions/NBA_<year>_transactions.html` | Completed trades (comparable-trade retrieval) | `make fetch-transactions` then `make import-transactions` |

To create `draft_picks/realgm_future_drafts.html`: open
https://basketball.realgm.com/nba/draft/future_drafts/ in your browser and save the page
(HTML only) to this folder.

**Half of what that page lists cannot become ownership, and RosterLab does not pretend
otherwise.** On the 2026-07-28 snapshot the importer reads 394 entries: 184 are
unconditional transfers and become verified ownership (92 distinct picks); 161 are swaps,
33 are protected and 16 are conditional. Those 103 are stored with their source sentence
verbatim, `is_verified = false`, and a `conveyance` class, and each raises a
`draft_pick_unresolved_conveyance` warning. A team with any unresolved entry has its
Stepien-rule verdict reported as `unavailable`, naming the clause — because a swap's
outcome depends on two teams' finishes and a protected pick may not convey at all.

Run `make pick-ownership YEAR=2029` to see, per team, what is verified and what is not.

To create `contracts/players.html`: open
https://www.basketball-reference.com/contracts/players.html in your browser and save
the page (HTML only) to this folder. RosterLab parses your snapshot locally — it
never scrapes the site on page load — and records the file date as the data's
provenance. Unparseable rows are preserved for review, never corrected or invented.


## Transactions

`make fetch-transactions FROM=2017 TO=2026` downloads one Basketball-Reference season page
per season into `transactions/`. It is the only fetcher in this repository, and it exists
because ten pages is too many to save by hand and they change as the season advances.

The fetch reads its constraints from the source's own published policy rather than
assuming them. `basketball-reference.com/robots.txt` allows `/leagues/` for `User-agent: *`
and publishes `Crawl-delay: 3`; the fetcher waits **3.5 seconds** between requests, sends a
user agent that names the project, issues exactly one request per season page and follows
no links. A `provenance.json` sidecar records each page's URL, HTTP status, byte count,
SHA-256 and retrieval timestamp, so any parsed row can be traced to the exact bytes it came
from. Pages already present are not re-requested unless `FORCE=1` is passed.

The same robots file **disallows** `*/on-off/` and `*/lineups/`. That is one of the two
measurements behind R6's decision not to build a lineup-aware fit model — the other is that
the local Kaggle `nbadb` play-by-play ends on 2023-06-12, before the first season RosterLab
models. See `docs/limitations.md`.

`make import-transactions` parses what was fetched. On the 2016-17 … 2025-26 corpus that is
**565 trades**, 2,568 asset legs, 69 of them involving three or more teams. **1,341 of 1,500
player legs (89.4 %) resolve to a player in this database**; the 159 that do not are almost
entirely draft-rights players who never appeared in an NBA game, and each is filed as a
`historical_trade_unresolved_player` warning rather than fuzzy-matched. Five asset phrases
across ten seasons have no grammar the parser recognizes; they are kept verbatim on the
trade and filed as warnings.
