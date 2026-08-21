"""Backfill migrations for tables created out-of-band (finforge-15).

Five tables defined in api/models/db_models.py existed only in the live prod
DB (created outside alembic): natebot_queue, cron_logs, drawdown_predictions,
portfolio_analysis, portfolio_targets. A fresh `alembic upgrade head` would
silently lack them and every writer swallows the resulting errors.

Idempotent: CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS, so this
no-ops on the already-provisioned prod DB (same pattern as
add_investment_transactions.py). DDL mirrors the live prod schema exactly
(pg_dump --schema-only, 2026-08-20).

Revision ID: b5c7d9e1f024
Revises: a7c3e5f1d926
"""

from alembic import op

revision = "b5c7d9e1f024"
down_revision = "a7c3e5f1d926"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS natebot_queue (
            id uuid NOT NULL PRIMARY KEY,
            priority varchar(10) NOT NULL DEFAULT 'normal',
            category varchar(50) NOT NULL,
            text text NOT NULL,
            delivered boolean NOT NULL DEFAULT false,
            delivered_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_natebot_queue_category ON natebot_queue (category);
        CREATE INDEX IF NOT EXISTS ix_natebot_queue_created_at ON natebot_queue (created_at);
        CREATE INDEX IF NOT EXISTS ix_natebot_queue_delivered ON natebot_queue (delivered);

        CREATE TABLE IF NOT EXISTS cron_logs (
            id uuid NOT NULL PRIMARY KEY,
            job_name varchar(100) NOT NULL,
            level varchar(10) NOT NULL,
            message text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_cron_logs_created_at ON cron_logs (created_at);
        CREATE INDEX IF NOT EXISTS ix_cron_logs_job_name ON cron_logs (job_name);
        CREATE INDEX IF NOT EXISTS ix_cron_logs_level ON cron_logs (level);

        CREATE TABLE IF NOT EXISTS drawdown_predictions (
            id uuid NOT NULL PRIMARY KEY,
            symbol varchar(20) NOT NULL,
            prediction_date date NOT NULL,
            drawdown_probability numeric(5,4) NOT NULL,
            model_version varchar(50) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_drawdown_pred_sym_date UNIQUE (symbol, prediction_date)
        );
        CREATE INDEX IF NOT EXISTS ix_drawdown_pred_date ON drawdown_predictions (prediction_date);
        CREATE INDEX IF NOT EXISTS ix_drawdown_pred_symbol ON drawdown_predictions (symbol);

        CREATE TABLE IF NOT EXISTS portfolio_analysis (
            id uuid NOT NULL PRIMARY KEY,
            account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            analysis_date date NOT NULL,
            symbol varchar(20) NOT NULL,
            market_value numeric(12,2),
            cost_basis numeric(12,2),
            unrealized_gl numeric(12,2),
            pct_of_portfolio numeric(8,4),
            target_pct numeric(5,2),
            drift_pct numeric(8,4),
            annualized_vol numeric(8,4),
            beta numeric(8,4),
            drawdown_from_high numeric(8,4),
            tlh_candidate boolean NOT NULL DEFAULT false,
            wash_sale_risk boolean NOT NULL DEFAULT false,
            wash_sale_details text,
            hhi numeric(8,4),
            top5_concentration numeric(8,4),
            weighted_volatility numeric(8,4),
            max_drawdown numeric(8,4),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_portfolio_analysis UNIQUE (account_id, analysis_date, symbol)
        );
        CREATE INDEX IF NOT EXISTS ix_portfolio_analysis_account_id ON portfolio_analysis (account_id);
        CREATE INDEX IF NOT EXISTS ix_portfolio_analysis_date ON portfolio_analysis (analysis_date);

        CREATE TABLE IF NOT EXISTS portfolio_targets (
            id uuid NOT NULL PRIMARY KEY,
            account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            symbol varchar(20) NOT NULL,
            target_pct numeric(5,2) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_portfolio_target_acct_sym UNIQUE (account_id, symbol)
        );
        CREATE INDEX IF NOT EXISTS ix_portfolio_targets_account_id ON portfolio_targets (account_id);
        """
    )


def downgrade() -> None:
    # Intentionally a no-op: these tables predate this migration in prod and
    # hold live operational data; dropping them on downgrade would be wrong.
    pass
