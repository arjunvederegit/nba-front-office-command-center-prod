# User-imported contract data (optional)

`nba_api` provides NBA.com basketball data but **not** contract or salary detail.
TradeLab therefore treats contracts as an optional, separately-provided dataset behind
the `ContractProvider` interface.

Without contract data the application still works: rosters, statistics, impact models,
fit and timeline analysis all function, but salary matching is labeled **unavailable**
and trade legality is reported as **conditionally valid** at best — never certified.

## Enabling the file provider

1. Obtain contract data you lawfully possess (e.g. your own tracked dataset or a
   licensed export whose terms permit local analytical use).
2. Save it here as `contracts.csv` (this directory is gitignored — the file must never
   be committed or redistributed).
3. Configure `.env`:

```env
CONTRACT_DATA_PROVIDER=file
CONTRACT_DATA_FILE=data/contracts/contracts.csv
```

4. Run `make sync-data` (or `python -m app.cli sync-contracts`).

## Expected CSV schema

| column               | type    | required | notes                                        |
| -------------------- | ------- | -------- | -------------------------------------------- |
| player_name          | string  | yes      | matched against nba_api player identities    |
| nba_player_id        | int     | no       | preferred when present — exact match         |
| team_abbreviation    | string  | yes      | e.g. BOS                                     |
| season               | string  | yes      | league year, e.g. 2025-26                    |
| salary               | int     | yes      | cap salary in whole dollars                  |
| contract_type        | string  | no       | standard, two-way, exhibit-10                |
| signed_date          | date    | no       | enables recently-signed trade restrictions   |
| no_trade_clause      | bool    | no       |                                              |
| player_option        | bool    | no       |                                              |
| team_option          | bool    | no       |                                              |
| guaranteed           | int     | no       | guaranteed portion in dollars                |
| source_name          | string  | yes      | shown in the UI as provenance                |
| source_date          | date    | yes      | shown in the UI as data freshness            |

Rows failing validation are rejected and logged to `data_quality_issues` — they are
never silently corrected. The UI always displays `source_name` and `source_date` for
contract-derived values and never describes them as NBA.com data.
