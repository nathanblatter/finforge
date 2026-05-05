"""Add watchlists, watchlist_items, and market_data_cache tables.

Revision ID: c4a2e7f8b301
Revises: add_mfa_fields
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "c4a2e7f8b301"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- watchlists --
    op.create_table(
        "watchlists",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
    )

    # -- watchlist_items --
    op.create_table(
        "watchlist_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("watchlist_id", UUID(as_uuid=True), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
    )

    # -- market_data_cache --
    op.create_table(
        "market_data_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False, unique=True),
        sa.Column("last_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("open_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("high_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("low_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("close_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("volume", sa.BigInteger, nullable=True),
        sa.Column("net_change", sa.Numeric(12, 4), nullable=True),
        sa.Column("net_change_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("high_52w", sa.Numeric(12, 2), nullable=True),
        sa.Column("low_52w", sa.Numeric(12, 2), nullable=True),
        sa.Column("pe_ratio", sa.Numeric(12, 4), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(8, 4), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("market_data_cache")
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
