"""de-duplicate model_versions and add UNIQUE(model_name, version)

Revision ID: b1a7c93f4e02
Revises: ac4624025dbb
Create Date: 2026-07-28 03:05:00.000000

A version string is supposed to identify a model. It did not: `train_all` stamped every
model in a run with one `datetime.now().strftime("v%Y%m%d%H%M")`, so a single training
run wrote `v202607210204` three times and `model_versions` accumulated rows that no
query could tell apart. R1-9 replaces the string with a content hash; this migration
clears the way for the constraint that keeps it honest.

De-duplication rule, applied per (model_name, version):

- keep the **active** row if exactly one is active, otherwise the most recently trained;
- **delete** the estimates belonging to the rows that go, then delete the rows.

The estimates are deleted rather than re-pointed on purpose. Rows sharing a version
string came from *different* training runs and carry different numbers; re-pointing
would merge two models' outputs under one identity, which is worse than removing them.
Nothing reachable is lost: `EvaluationService._impacts` only ever reads the active
version, so superseded estimates were already unreachable — 1,536 rows for 512 players
across three versions. `train_all` now garbage-collects them on every run.

Measured on the development database: 9 model_versions rows over 6 distinct
(model_name, version) pairs, and 1,536 impact estimates of which 1,024 were orphaned.
"""

import sqlalchemy as sa
from alembic import op

revision = "b1a7c93f4e02"
down_revision = "ac4624025dbb"
branch_labels = None
depends_on = None


def _rows_to_drop(connection) -> list[str]:
    rows = (
        connection.execute(
            sa.text(
                "SELECT id, model_name, version, is_active, trained_at, created_at "
                "FROM model_versions ORDER BY model_name, version"
            )
        )
        .mappings()
        .all()
    )
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["model_name"], row["version"]), []).append(dict(row))

    drop: list[str] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        active = [m for m in members if m["is_active"]]
        keep = (
            active[0]
            if len(active) == 1
            else max(
                members,
                key=lambda m: (
                    str(m["trained_at"] or ""),
                    str(m["created_at"] or ""),
                    str(m["id"]),
                ),
            )
        )
        drop.extend(m["id"] for m in members if m["id"] != keep["id"])
    return drop


def upgrade() -> None:
    connection = op.get_bind()
    for model_version_id in _rows_to_drop(connection):
        connection.execute(
            sa.text("DELETE FROM player_impact_estimates WHERE model_version_id = :id"),
            {"id": model_version_id},
        )
        connection.execute(
            sa.text("DELETE FROM model_versions WHERE id = :id"), {"id": model_version_id}
        )
    with op.batch_alter_table("model_versions") as batch:
        batch.create_unique_constraint("uq_model_version", ["model_name", "version"])


def downgrade() -> None:
    with op.batch_alter_table("model_versions") as batch:
        batch.drop_constraint("uq_model_version", type_="unique")
