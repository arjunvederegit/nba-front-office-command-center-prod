# Data sources

## Primary (required): NBA.com via swar/nba_api

Package `nba_api==1.11.4` (pinned). Upstream services: `stats.nba.com` and
`cdn.nba.com`. All access flows through `backend/app/integrations/nba_api/` with
rate limiting (0.75 s min interval, concurrency 2), bounded retries with jitter, a
per-endpoint circuit breaker, response caching, and schema validation. Respectful
usage is a design constraint: no aggressive parallel scraping, polling only for
data the product displays.

### Endpoints in production use

| Endpoint | Purpose | Cadence |
| --- | --- | --- |
| `stats.static.teams` / `players` | identity records (package-bundled, no network) | each sync |
| `CommonTeamRoster` | current rosters + bio enrichment | 6 h (worker) |
| `LeagueStandingsV3` | standings (current + history seasons) | 6 h |
| `LeagueDashPlayerStats` (Base, Advanced) | player season stats, 3 seasons | daily |
| `PlayerEstimatedMetrics` | optional enrichment (documented fallback) | daily |
| `LeagueDashTeamStats` (Base, Advanced) | team season stats | daily |
| `LeagueGameLog` (team) | completed games | daily |
| `live.scoreboard/boxscore/playbyplay` | live data — **disabled by default** (`LIVE_DATA_ENABLED`); this build's network is edge-blocked by cdn.nba.com, which surfaces as a classified `blocked` provider error, honestly shown | in-season only |

Every ingested record stores: provider, upstream, endpoint class, source record ID,
request/retrieval timestamps, season, package version, and ingestion run ID.

### Contract tests

`integrations/nba_api/schemas.py` declares required datasets/columns per endpoint;
violations raise `ProviderSchemaError` before anything reaches the database. Live
contract verification is manual/scheduled only — ordinary CI never depends on
NBA.com availability (unit tests use recorded/synthetic fixtures).

## Secondary (optional): contracts

`nba_api` provides no contract data. Interface: `ContractProvider`
(`integrations/contracts/`). Bundled implementation: `file` — a user-imported CSV
the user lawfully possesses (schema + legal notes in
[data/contracts/README.md](../data/contracts/README.md)); rows failing validation
are rejected into `data_quality_issues`, never corrected. Contract-derived values
always display their own `source_name`/`source_date` and are never described as
NBA.com data. **No provider configured ⇒ salary features are unavailable, and
legality caps at `conditionally_valid`.**

## Not sourced (by design)

- **Injuries** — no provider bundled; availability uses historical games played
  only and is labeled as such.
- **Verified draft-pick ownership** — no authoritative provider; picks in trades
  are labeled hypotheticals; Stepien compliance is never certified.
- **Cap parameters** are not scraped: version-controlled YAML in
  `backend/app/config/cap_rules/`, each value carrying league year, effective date,
  source name/URL, and verification timestamp (2025-26 and 2026-27 verified against
  the NBA's official June announcements).

## Licensing posture

No NBA data is committed to this repository; everything is fetched at runtime by the
operator under NBA.com's terms. Test fixtures are small synthetic records clearly
marked as fixtures. Logs avoid wholesale provider payloads.
