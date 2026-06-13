"""Add tags array to transactions.

Revision ID: c7e5a3d1b948
Revises: b8c6d4e2f937
Create Date: 2026-06-12
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "c7e5a3d1b948"
down_revision = "b8c6d4e2f937"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the column may already exist if pre-applied out of band.
    op.execute(
        "ALTER TABLE transactions "
        "ADD COLUMN IF NOT EXISTS tags VARCHAR(50)[] NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE transactions DROP COLUMN IF EXISTS tags")
