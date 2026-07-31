"""Add fire_settings table (FIRE / retirement projector assumptions).

Revision ID: d4f6a8c1e935
Revises: f2a9c6e4d135
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "d4f6a8c1e935"
down_revision = "f2a9c6e4d135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fire_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("current_age", sa.Integer, nullable=True),
        sa.Column("target_retirement_age", sa.Integer, nullable=False, server_default="65"),
        sa.Column("expected_annual_spend", sa.Numeric(12, 2), nullable=True),
        sa.Column("withdrawal_rate", sa.Numeric(5, 4), nullable=False, server_default="0.04"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("fire_settings")
