# Kaggle Historical NBA Database Setup

TradeLab can enrich player records from the public Kaggle dataset
[`wyattowalsh/basketball`](https://www.kaggle.com/datasets/wyattowalsh/basketball),
a SQLite snapshot (`nba.sqlite`) of NBA history: game-level results back to 1946,
team/player identity tables, `draft_history`, and `common_player_info`.

## What the import actually uses

The importer (`app/integrations/kaggle_nba/importer.py`) treats Kaggle as a
**secondary** source and reads only two tables:

| Kaggle table         | Player fields filled (only where currently NULL)   |
| -------------------- | -------------------------------------------------- |
| `draft_history`      | `draft_year`, `draft_round`, `draft_number`        |
| `common_player_info` | `birth_date`, `height_inches`, `weight_lbs`        |

Rows are matched on `person_id == players.nba_player_id`. Values already present
(nba_api source hierarchy) are **never overwritten**; disagreements are recorded
as `kaggle_source_conflict` rows in `data_quality_issues`. Unparseable values are
rejected and recorded (`kaggle_unparseable_row`), never guessed. The dataset is
registered in `data_sources` as `kaggle_basketball` with the local path, a
sha256 checksum of the file's first 1 MB, and the download timestamp.

## Authentication

The dataset is public: `kagglehub` needs **no credentials** for anonymous
download. On corporate/restricted networks (or if you hit 401/403 responses),
set `KAGGLE_USERNAME` and `KAGGLE_KEY` (from kaggle.com → Account → Create New
API Token) in the environment before running the import.

## Cache location

By default `kagglehub` caches under `~/.cache/kagglehub/`. To relocate it (CI,
servers, small home partitions), either:

- set `KAGGLE_DATA_DIR` in the backend `.env` (the `kaggle_data_dir` setting) —
  the importer exports it as `KAGGLEHUB_CACHE` before touching kagglehub, or
- export `KAGGLEHUB_CACHE=/path/to/cache` yourself.

The importer finds `nba.sqlite` anywhere under the versioned cache directory, so
a cache pre-seeded from another machine works without a download.

## Running the import

```bash
cd backend
.venv/bin/python -m app.cli import-kaggle
```

Re-running is safe: only NULL fields are filled, and the `data_sources`
registration is updated in place.

## Storage expectations

The dataset is **multi-GB** (the SQLite file alone is several GB, plus
kagglehub's download archive during fetch). Ensure roughly 10 GB free before the
first download. Subsequent runs reuse the cache.

## Graceful failure

Absence of data is treated as an honest state, never fabricated around:

- If the download fails (no network, auth wall, disk full) or the cache is
  empty, the import records a **succeeded** sync run whose detail notes the
  dataset was not available, and returns `{"status": "unavailable", "hint": ...}`.
  Nothing is written to player rows.
- If the upstream schema drifts (a table or its `person_id` column disappears),
  the affected table is skipped and listed under `missing_tables` in the run
  detail; the rest of the import proceeds.
- Per-table counts (rows read, matched, fields filled, conflicts, rejected) are
  stored on the sync run and visible via `/data-health`.
