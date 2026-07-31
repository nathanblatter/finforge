"""Add financial_health_snapshots table.

Revision ID: d3f8a1c2b569
Revises: d4f6a8c1e935
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "d3f8a1c2b569"
down_revision = "d4f6a8c1e935"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_health_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("composite_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("savings_rate_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("savings_rate_value", sa.Numeric(8, 2), nullable=True),
        sa.Column("emergency_fund_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("emergency_fund_months", sa.Numeric(8, 2), nullable=True),
        sa.Column("expense_volatility_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("expense_volatility_cv", sa.Numeric(8, 4), nullable=True),
        sa.Column("allocation_drift_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("allocation_drift_value", sa.Numeric(8, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_financial_health_snapshots_snapshot_date",
        "financial_health_snapshots",
        ["snapshot_date"],
    )
    op.create_unique_constraint(
        "uq_financial_health_snapshot_date",
        "financial_health_snapshots",
        ["snapshot_date"],
    )


def downgrade() -> None:
    op.drop_table("financial_health_snapshots")
