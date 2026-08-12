# data/imports/

Drop-zone for user-supplied import files (gitignored — nothing here is committed).

| File | Used by | Command |
| --- | --- | --- |
| `nba_player_stats_2026.csv` | 2025-26 season-totals import (Player Lab) | `make import-stats-csv` |
| `contracts/players.html` | Basketball-Reference contracts snapshot parser (Cap Lab, salary rules) | set `CONTRACT_DATA_PROVIDER=bbref_snapshot`, then `make sync-data` |
| `draft_picks/realgm_future_drafts.html` | Draft-pick ownership (Stepien rule, asset valuation) | `make import-draft-picks` |

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
