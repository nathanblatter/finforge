"""Drop the users/passkeys tables; identity is the Squawk subject.

FinForge no longer has app users: sign-in is through Squawk and the session
JWT's `sub` is the Squawk subject string ("owner" today, "usr:<id>" later).
The three per-user tables (watchlists, chat_messages, drawdown_favorites)
switch from a `user_id` FK to a `subject TEXT` column. Every existing row
belongs to Nathan, so they are backfilled to 'owner'.

Idempotent: every step checks the current state first, so it is safe against
a database where add_users_table/add_passkeys ran, where this migration was
partially applied, or where it already completed.

Revision ID: e1f3a5c7b920
Revises: d4e6f8a0b319
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e1f3a5c7b920"
down_revision = "d4e6f8a0b319"
branch_labels = None
depends_on = None

OWNER_SUBJECT = "owner"

# table -> (second unique column, old unique constraint, new unique constraint)
SCOPED_TABLES = {
    "watchlists": ("name", "uq_watchlist_user_name", "uq_watchlist_subject_name"),
    "chat_messages": (None, None, None),
    "drawdown_favorites": ("symbol", "uq_drawdown_favorite_user_symbol", "uq_drawdown_favorite_subject_symbol"),
}


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in _inspector().get_columns(table)}


def _constraint_exists(table: str, name: str) -> bool:
    return op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = :table AND c.conname = :name"
        ),
        {"table": table, "name": name},
    ).first() is not None


def upgrade() -> None:
    for table, (col, old_uq, new_uq) in SCOPED_TABLES.items():
        if not _has_table(table):
            continue
        cols = _columns(table)

        # 1. subject column, backfilled to the owner (every row is Nathan's).
        if "subject" not in cols:
            op.add_column(table, sa.Column("subject", sa.Text(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET subject = :s WHERE subject IS NULL").bindparams(s=OWNER_SUBJECT))
        op.alter_column(table, "subject", existing_type=sa.Text(), nullable=False)

        # 2. constraints/indexes keyed on user_id -> subject.
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_user_id_fkey")
        if old_uq:
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {old_uq}")
        if new_uq and not _constraint_exists(table, new_uq):
            op.create_unique_constraint(new_uq, table, ["subject", col])
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_user_id")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_subject ON {table} (subject)")

        # 3. the FK column itself.
        if "user_id" in cols:
            op.drop_column(table, "user_id")

    # 4. no more app users. passkeys references users, so it goes first.
    op.execute("DROP TABLE IF EXISTS passkeys")
    op.execute("DROP TABLE IF EXISTS users")


def downgrade() -> None:
    """Best effort: recreate empty users/passkeys and a nullable user_id on the
    scoped tables. Rows keep their subject; nothing can map them back to a
    users.id, so the FK is restored without data."""
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("username", sa.String(50), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(255), nullable=True),
            sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("totp_secret", sa.String(64), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if not _has_table("passkeys"):
        op.create_table(
            "passkeys",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
            sa.Column("public_key", sa.LargeBinary(), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("transports", sa.ARRAY(sa.String(32)), nullable=True),
            sa.Column("name", sa.String(100), nullable=False, server_default="Passkey"),
            sa.Column("aaguid", sa.String(36), nullable=True),
            sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        )

    for table, (col, old_uq, new_uq) in SCOPED_TABLES.items():
        if not _has_table(table):
            continue
        cols = _columns(table)
        if "user_id" not in cols:
            op.add_column(table, sa.Column("user_id", UUID(as_uuid=True), nullable=True))
            op.create_foreign_key(f"{table}_user_id_fkey", table, "users", ["user_id"], ["id"], ondelete="CASCADE")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id)")
        if new_uq:
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {new_uq}")
        if old_uq and not _constraint_exists(table, old_uq):
            op.create_unique_constraint(old_uq, table, ["user_id", col])
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_subject")
        if "subject" in cols:
            op.drop_column(table, "subject")
