"""Track option contracts: asset_type on holdings/investment_transactions,
position_effect on investment_transactions. Backfills existing OCC-symbol rows.

Revision ID: d4e6f8a0b319
Revises: c9d1e3f5a207
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e6f8a0b319"
down_revision = "c9d1e3f5a207"
branch_labels = None
depends_on = None

# OCC option symbol: root (<=6, space padded) + YYMMDD + C/P + strike*1000 (8 digits)
_OCC_PATTERN = r"^[A-Z][A-Z0-9.]{0,5}\s*[0-9]{6}[CP][0-9]{7,8}$"


def upgrade() -> None:
    # OCC option symbols are 21 chars; String(20) silently dropped the last
    # strike digit. Widen before backfilling asset_type.
    op.alter_column("holdings", "symbol", existing_type=sa.String(20), type_=sa.String(32))
    op.alter_column(
        "investment_transactions", "symbol", existing_type=sa.String(20), type_=sa.String(32),
        existing_nullable=True,
    )
    op.add_column(
        "holdings",
        sa.Column("asset_type", sa.String(20), nullable=False, server_default="EQUITY"),
    )
    op.add_column(
        "investment_transactions",
        sa.Column("asset_type", sa.String(20), nullable=False, server_default="EQUITY"),
    )
    op.add_column(
        "investment_transactions",
        sa.Column("position_effect", sa.String(10), nullable=True),
    )
    op.execute(f"UPDATE holdings SET asset_type = 'OPTION' WHERE symbol ~ '{_OCC_PATTERN}'")
    op.execute(
        f"UPDATE investment_transactions SET asset_type = 'OPTION' WHERE symbol ~ '{_OCC_PATTERN}'"
    )


def downgrade() -> None:
    op.alter_column(
        "investment_transactions", "symbol", existing_type=sa.String(32), type_=sa.String(20),
        existing_nullable=True,
    )
    op.alter_column("holdings", "symbol", existing_type=sa.String(32), type_=sa.String(20))
    op.drop_column("investment_transactions", "position_effect")
    op.drop_column("investment_transactions", "asset_type")
    op.drop_column("holdings", "asset_type")
