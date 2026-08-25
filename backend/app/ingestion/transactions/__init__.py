"""Historical NBA transaction ingestion (Basketball-Reference season pages).

`nba_api` publishes no transaction history, so — exactly like contracts and draft picks —
this is an optional secondary dataset. The raw pages stay on the machine that fetched them
(`data/imports/` is gitignored in full); only normalized, attributable rows reach the
database.
"""
