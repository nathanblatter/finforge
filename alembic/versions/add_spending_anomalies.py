"""Add spending_anomalies table.

Revision ID: a9d7e5f3b821
Revises: f7d5c3e9a204
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "a9d7e5f3b821"
down_revision = "f7d5c3e9a204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spending_anomalies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("z_score", sa.Numeric(8, 2), nullable=True),
        sa.Column("typical_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("is_dismissed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("spending_anomalies")
