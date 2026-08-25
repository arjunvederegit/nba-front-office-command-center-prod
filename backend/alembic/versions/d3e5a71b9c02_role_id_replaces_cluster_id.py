"""rename player_archetypes.cluster_id to role_id and distances to role_inputs

Revision ID: d3e5a71b9c02
Revises: c7f1d2a54e90
Create Date: 2026-07-28 23:55:00.000000

R4-3 retires k-means for a deterministic size-first rule chain, and the two columns that
carried k-means output no longer mean what they are named.

`cluster_id` held an arbitrary k-means cluster index whose numbering changed on every
retrain. It now holds a `role_id` from a frozen, append-only map, so the number is stable
across retrains and comparable across seasons — a genuinely different quantity that
deserves a different name.

`distances` held `{"own_cluster": <euclidean distance to the centroid>}`. A rule chain has
no centroids and no distances. The column becomes `role_inputs` and carries the values
that actually determined the branch, which is the question a reader of a role label
actually has: not "how far from a centroid" but "why this role".

Existing rows are preserved and renamed rather than dropped. Their contents are stale —
old cluster indices, old distances — and the next `make train` overwrites every row, but
destroying data in a migration to save one retrain is not a trade worth making.
"""

import sqlalchemy as sa
from alembic import op

revision = "d3e5a71b9c02"
down_revision = "c7f1d2a54e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a column in place, and this project's dev and e2e
    # databases are SQLite while production is Postgres. Batch works on both.
    with op.batch_alter_table("player_archetypes") as batch:
        batch.alter_column("cluster_id", new_column_name="role_id", existing_type=sa.Integer())
        batch.alter_column("distances", new_column_name="role_inputs", existing_type=sa.JSON())


def downgrade() -> None:
    with op.batch_alter_table("player_archetypes") as batch:
        batch.alter_column("role_id", new_column_name="cluster_id", existing_type=sa.Integer())
        batch.alter_column("role_inputs", new_column_name="distances", existing_type=sa.JSON())
