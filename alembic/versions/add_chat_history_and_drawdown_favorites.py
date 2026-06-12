"""Add chat_messages and drawdown_favorites tables.

Revision ID: d5b3f1a9c602
Revises: c4a2e7f8b301
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "d5b3f1a9c602"
down_revision = "c4a2e7f8b301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- chat_messages --
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )

    # -- drawdown_favorites --
    op.create_table(
        "drawdown_favorites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "symbol", name="uq_drawdown_favorite_user_symbol"),
    )


def downgrade() -> None:
    op.drop_table("drawdown_favorites")
    op.drop_table("chat_messages")
