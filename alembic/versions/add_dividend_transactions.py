"""Add dividend_transactions table (dividend & income calendar feature).

Revision ID: d3e9a1c5b642
Revises: c7e5a3d1b948
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "d3e9a1c5b642"
down_revision = "c7e5a3d1b948"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dividend_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("pay_date", sa.Date, nullable=False, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("activity_type", sa.String(20), nullable=False, server_default="dividend"),
        sa.Column("quantity_at_payment", sa.Numeric(15, 6), nullable=True),
        sa.Column("per_share_amount", sa.Numeric(12, 6), nullable=True),
        sa.Column("is_reinvested", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("reinvest_transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reinvest_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("schwab_activity_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("schwab_activity_id", name="uq_dividend_txn_schwab_activity_id"),
    )


def downgrade() -> None:
    op.drop_table("dividend_transactions")
