# data/imports/

Drop-zone for user-supplied import files (gitignored — nothing here is committed).

| File | Used by | Command |
| --- | --- | --- |
| `nba_player_stats_2026.csv` | 2025-26 season-totals import (Player Lab) | `make import-stats-csv` |
| `contracts/players.html` | Basketball-Reference contracts snapshot parser (Cap Lab, salary rules) | set `CONTRACT_DATA_PROVIDER=bbref_snapshot`, then `make sync-data` |

To create `contracts/players.html`: open
https://www.basketball-reference.com/contracts/players.html in your browser and save
the page (HTML only) to this folder. RosterLab parses your snapshot locally — it
never scrapes the site on page load — and records the file date as the data's
provenance. Unparseable rows are preserved for review, never corrected or invented.
