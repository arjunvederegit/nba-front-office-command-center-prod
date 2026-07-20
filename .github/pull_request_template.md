## What

<!-- What does this change do? -->

## Why

<!-- Motivation / linked issue -->

## Data honesty checklist

- [ ] No synthetic NBA data introduced into production paths
- [ ] Provenance fields populated for any new provider-derived records
- [ ] Unavailable data surfaces an explicit state (never a fabricated value)
- [ ] No secrets or licensed bulk data committed

## Testing

- [ ] Unit tests added/updated
- [ ] `make lint` passes
- [ ] `make test` passes
