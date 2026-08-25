"""record how a traded draft pick conveys, not just that it was traded

Revision ID: e5c81f4a7b30
Revises: d3e5a71b9c02
Create Date: 2026-08-12 19:20:00.000000

R5-2 imports pick ownership from a RealGM future-drafts snapshot. Roughly half of the
traded picks in that source do not convey unconditionally: they are swaps, they are
protected for a range of selections, or they convey only if some other pick conveys first.

`draft_picks` had `is_verified` and a free-text `protections`, which cannot express the
difference between "this pick is Atlanta's, unconditionally, and now belongs to San
Antonio" and "one of these three teams will receive the more favourable of two picks,
protected 1-4, and if it lands in that range the obligation is extinguished". Storing both
as `is_verified = False` loses the reason, and storing the second as `True` would be a
fabrication.

`conveyance` names the class, so the Stepien rule can certify the picks it can certify and
report `unavailable` — naming the specific unresolved entries — for the rest.

Nullable with no default. An existing row was written before this distinction existed, and
its conveyance is genuinely unknown; back-filling it with 'unconditional' would invent
exactly the certainty this column exists to withhold.
"""

import sqlalchemy as sa
from alembic import op

revision = "e5c81f4a7b30"
down_revision = "d3e5a71b9c02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("draft_picks", sa.Column("conveyance", sa.String(length=20), nullable=True))
    op.add_column("draft_picks", sa.Column("source_text", sa.Text(), nullable=True))
    op.create_index(
        "ix_draft_picks_year_round",
        "draft_picks",
        ["draft_year", "round_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_draft_picks_year_round", table_name="draft_picks")
    op.drop_column("draft_picks", "source_text")
    op.drop_column("draft_picks", "conveyance")
