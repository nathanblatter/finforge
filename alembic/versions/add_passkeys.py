"""Add passkeys table; make users.password_hash nullable (passkey-only accounts).

Revision ID: c9d1e3f5a207
Revises: b5c7d9e1f024
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c9d1e3f5a207"
down_revision = "b5c7d9e1f024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    op.create_table(
        "passkeys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transports", postgresql.ARRAY(sa.String(32)), nullable=True),
        sa.Column("name", sa.String(100), nullable=False, server_default="Passkey"),
        sa.Column("aaguid", sa.String(36), nullable=True),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_passkeys_user_id", "passkeys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_passkeys_user_id", table_name="passkeys")
    op.drop_table("passkeys")
    # Rows with NULL password_hash would violate NOT NULL; downgrade only if none exist.
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
