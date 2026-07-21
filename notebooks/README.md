# notebooks/

Exploratory analysis lives in the reproducible pipeline instead of notebooks:

- `make build-features` — feature coverage summary
- `make train` — model comparison + validation metrics (also persisted to
  `model_versions` and shown on /data-health)
- `make score` — team-needs computation

If you add notebooks, keep raw provider data out of committed outputs
(`jupyter nbconvert --clear-output` before committing).
