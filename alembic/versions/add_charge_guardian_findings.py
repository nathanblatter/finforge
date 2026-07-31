"""Add charge_guardian_findings table.

Revision ID: 6397796c1c71
Revises: d3f8a1c2b569
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID


# revision identifiers, used by Alembic.
revision = "6397796c1c71"
down_revision = "d3f8a1c2b569"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "charge_guardian_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # "duplicate_charge" | "new_subscription" | "trial_conversion" | "gray_charge_creep"
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("merchant", sa.String(255), nullable=False),
        # Suppression key: re-running the detectors will skip creating a row
        # whose dedupe_key already exists, so dismiss/mark-legit sticks.
        sa.Column("dedupe_key", sa.String(400), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
        sa.Column("evidence_transaction_ids", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        # "open" | "dismissed" | "legit"
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_charge_guardian_dedupe_key"),
    )
    op.create_index(
        "ix_charge_guardian_findings_status", "charge_guardian_findings", ["status"]
    )
    op.create_index(
        "ix_charge_guardian_findings_merchant_kind", "charge_guardian_findings", ["merchant", "kind"]
    )


def downgrade() -> None:
    op.drop_index("ix_charge_guardian_findings_merchant_kind", table_name="charge_guardian_findings")
    op.drop_index("ix_charge_guardian_findings_status", table_name="charge_guardian_findings")
    op.drop_table("charge_guardian_findings")
