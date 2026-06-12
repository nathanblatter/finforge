"""Add market_regimes table.

Revision ID: b8c6d4e2f937
Revises: a9d7e5f3b821
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "b8c6d4e2f937"
down_revision = "a9d7e5f3b821"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_regimes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("regime_date", sa.Date, nullable=False, unique=True),
        sa.Column("regime", sa.String(30), nullable=False),
        sa.Column("realized_vol_20d", sa.Numeric(8, 4), nullable=True),
        sa.Column("trend_60d", sa.Numeric(8, 4), nullable=True),
        sa.Column("sma20_vs_sma50", sa.Numeric(8, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("market_regimes")
