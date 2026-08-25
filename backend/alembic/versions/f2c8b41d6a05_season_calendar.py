"""record when each season was actually played, so a trade is not described by the future

Revision ID: f2c8b41d6a05
Revises: 7a7a8e16cd96
Create Date: 2026-08-24 16:20:00.000000

R7-1. `services/comparables.feature_season_for` decided a trade's feature season from the
calendar MONTH — July, August and September were "offseason", everything else "in-season".
That rule is wrong in three places at once, and every one of them is a look-ahead:

- 2020-21 began **22 December 2020**. Thirty-three November-2020 trades were being
  described by 2020-21 production that had not been played.
- Basketball-Reference files draft-night trades under the season about to start, so twelve
  **June-2024** trades carried the label 2024-25 and were described by it.
- Ten trades fall in **early October**, before a first game that lands 22-25 October.

The June-2024 case is not hypothetical and was not introduced by R7: those twelve trades
are inside the shipped three-season window and are being ranked against 2024-25 numbers
today.

The fix needs the season boundary as data. `season_calendar` holds one row per season with
the first and last regular-season game date, ingested from `LeagueGameLog` — the same
provider `standings` and `player_season_stats` come from — so the rule is derived rather
than assumed. Ten rows.

Reversible: the table drops cleanly and holds only ingested rows, which
`make sync-season-calendar` rebuilds. With it absent, `feature_season_for` falls back to
the month rule and says so.
"""
import sqlalchemy as sa
from alembic import op

revision = "f2c8b41d6a05"
down_revision = "7a7a8e16cd96"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "season_calendar",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("season", sa.String(length=10), nullable=False),
        sa.Column("first_game_date", sa.Date(), nullable=False),
        sa.Column("last_game_date", sa.Date(), nullable=False),
        sa.Column("game_count", sa.Integer(), nullable=False),
        sa.Column("source_provider", sa.String(length=50), nullable=False),
        sa.Column("source_record_id", sa.String(length=100), nullable=True),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season", name="uq_season_calendar"),
    )
    with op.batch_alter_table("season_calendar", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_season_calendar_season"), ["season"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("season_calendar", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_season_calendar_season"))
    op.drop_table("season_calendar")
