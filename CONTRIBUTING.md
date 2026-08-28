# Contributing

Thanks for your interest! Pivot is a portfolio project, but issues and PRs are
welcome.

## Ground rules (the honesty bar)

1. **No synthetic NBA data in production paths.** Fixtures live only under
   `backend/tests/fixtures/` / `frontend/tests/` and must be clearly marked.
2. **Missing data becomes an explicit unavailable state** — never an estimate, a
   default, or a hidden branch.
3. **Provenance or it didn't happen**: provider-derived rows populate the
   ProvenanceMixin columns; UI surfaces source + timestamp.
4. New CBA rules require: plain-English description, formula, source reference,
   coverage entry in `docs/cba-rule-coverage.md`, and unit tests for pass, fail,
   and unavailable paths.
5. Model changes require updated validation metrics in the model card and a new
   `model_versions` entry.

## Dev workflow

```bash
make setup && make migrate && make seed-config
make sync-data && make train && make score   # real data (network)
make dev                                     # :8000 + :3000
make lint && make test                       # must pass before a PR
```

CI runs ruff, mypy, pytest, eslint, tsc, vitest, next build, migration check, and
Docker builds — none of which may call NBA.com.

## Commit style

Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `docs:`, `chore:`); explain
*why* in the body when the change is behavioral.
