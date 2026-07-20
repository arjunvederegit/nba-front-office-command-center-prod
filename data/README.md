# data/

This directory intentionally ships **no NBA data**.

All NBA basketball data (teams, players, rosters, standings, statistics, games) is
retrieved at runtime from NBA.com via the [`nba_api`](https://github.com/swar/nba_api)
package and stored in your local database with full provenance
(provider, endpoint, parameters, retrieval timestamps, package version, ingestion run ID).

Raw provider payloads are **not** committed to this repository because NBA.com's terms
do not clearly permit redistribution. To populate your own database:

```bash
make setup
make migrate
make seed-config   # load salary-cap parameters (version-controlled YAML, officially sourced)
make sync-data     # fetch current NBA data from NBA.com via nba_api (network required)
make train         # build features, train impact model, compute archetypes/needs
```

## Subdirectories

- `contracts/` — optional user-imported contract/salary file. `nba_api` does not provide
  contract data; see `contracts/README.md` for the expected schema and legal notes.
  Files placed here are gitignored and never redistributed.
- `snapshots/` — local database snapshots (gitignored).

## Test fixtures are not data

`backend/tests/fixtures/` contains small, sanitized, recorded response excerpts used only
by deterministic tests. They are clearly marked as fixtures, are never loaded by
production configuration, and are not presented in the application.
