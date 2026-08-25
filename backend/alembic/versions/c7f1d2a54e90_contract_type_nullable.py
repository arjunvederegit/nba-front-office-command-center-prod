"""make contracts.contract_type nullable and clear provider-asserted "standard"

Revision ID: c7f1d2a54e90
Revises: b1a7c93f4e02
Create Date: 2026-07-28 20:40:00.000000

`contract_type` was NOT NULL with a `"standard"` default, so every import asserted that
every contract it wrote was a standard deal. No provider actually reports this: the
Basketball-Reference contracts page does not distinguish two-way from standard, and its
886 rows were all stamped `"standard"` on the way in.

Two rules read the column, and both were made *permissive* by the assertion (C9):

- `ROSTER_SIZE` gates `types_known` on `all(contract_type is not None)`, so the import
  flipped all 30 teams from `(warning, medium)` to `(pass, high)`. A 14-man roster of 11
  standard + 3 two-way — illegal — would have reported `pass` at high confidence.
- Two-way salaries are excluded from salary matching. Counting one as standard inflates
  `outgoing_salary`, inflates the `maximum_incoming` it implies, and approves trades the
  engine should refuse.

NULL now means *unknown*, which is what the data is. The `file` CSV provider still
supplies a real value when the curator has one, and only then do those rules speak.

The data migration clears existing `"standard"` values **only for rows whose provider
cannot report the field** (identified by `source_name`), so a hand-curated CSV import
that genuinely recorded "standard" is left intact.
"""

import sqlalchemy as sa
from alembic import op

revision = "c7f1d2a54e90"
down_revision = "b1a7c93f4e02"
branch_labels = None
depends_on = None

# Providers that emit no contract-type information. Their "standard" values were the
# column default, not an observation.
ASSERTING_SOURCES = ("basketball-reference.com contracts snapshot",)


def upgrade() -> None:
    with op.batch_alter_table("contracts") as batch:
        batch.alter_column(
            "contract_type",
            existing_type=sa.String(length=30),
            nullable=True,
            server_default=None,
        )

    contracts = sa.table(
        "contracts",
        sa.column("contract_type", sa.String),
        sa.column("source_name", sa.String),
    )
    op.execute(
        contracts.update()
        .where(contracts.c.contract_type == "standard")
        .where(contracts.c.source_name.in_(ASSERTING_SOURCES))
        .values(contract_type=None)
    )


def downgrade() -> None:
    # Restoring NOT NULL requires a value, and the only one available is the assertion
    # this migration removed. Writing it back is explicitly part of the downgrade.
    contracts = sa.table("contracts", sa.column("contract_type", sa.String))
    op.execute(
        contracts.update().where(contracts.c.contract_type.is_(None)).values(contract_type="standard")
    )
    with op.batch_alter_table("contracts") as batch:
        batch.alter_column(
            "contract_type",
            existing_type=sa.String(length=30),
            nullable=False,
            server_default="standard",
        )
