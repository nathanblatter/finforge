"""Add investment_transactions — lot-level Schwab activity (trades, dividends, interest).

Backs the Tax Center's per-lot realized gains, quarterly estimated-tax tracker,
and 1099 reconciliation. Populated by the schwab_sync cron from
/accounts/{hash}/transactions (up to a 1-year window, includes quantity & price
that the orders sync lacks).

Revision ID: d8f6b4c2a059
Revises: c7e5a3d1b948
Create Date: 2026-07-30
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "d8f6b4c2a059"
down_revision = "c7e5a3d1b948"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the table may already exist if pre-applied out of band.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS investment_transactions (
            id UUID PRIMARY KEY,
            account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            schwab_activity_id VARCHAR(64) NOT NULL,
            txn_type VARCHAR(40) NOT NULL,
            action VARCHAR(10),
            trade_date DATE NOT NULL,
            settlement_date DATE,
            symbol VARCHAR(20),
            description TEXT,
            quantity NUMERIC(15, 6),
            price NUMERIC(14, 4),
            amount NUMERIC(14, 2) NOT NULL,
            fees NUMERIC(12, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_investment_txn_activity UNIQUE (schwab_activity_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_investment_transactions_account_id "
        "ON investment_transactions (account_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_investment_transactions_trade_date "
        "ON investment_transactions (trade_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_investment_transactions_symbol "
        "ON investment_transactions (symbol)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS investment_transactions")
