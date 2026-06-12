"""Add transactions.category_overridden and category_rules table.

Revision ID: f7d5c3e9a204
Revises: e6c4a2b8d713
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "f7d5c3e9a204"
down_revision = "e6c4a2b8d713"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("category_overridden", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "category_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("merchant", name="uq_category_rule_merchant"),
    )


def downgrade() -> None:
    op.drop_table("category_rules")
    op.drop_column("transactions", "category_overridden")
