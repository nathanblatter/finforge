"""Add cashflow_settings table for the cash-flow runway forecast.

Revision ID: f2a9c6e4d135
Revises: d3e9a1c5b642
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "f2a9c6e4d135"
down_revision = "d3e9a1c5b642"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cashflow_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("floor_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("lead_time_days", sa.BigInteger, nullable=False, server_default="14"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("cashflow_settings")
