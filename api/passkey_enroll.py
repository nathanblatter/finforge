"""Issue a one-time passkey enrollment link for a user (run inside the API container).

    docker compose exec finforge-api python passkey_enroll.py nathan
    docker compose exec finforge-api python passkey_enroll.py nathan --disable-password

The link opens /passkeys/enroll, which registers a passkey using only the
short-lived enrollment token — no password or session needed. This is the
break-glass path when a password is lost or has been removed.
"""

import argparse
import sys

from auth import create_passkey_enroll_token
from config import settings
from database import SessionLocal
from models.db_models import User


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--ttl", type=int, default=15, help="link lifetime in minutes (default 15)")
    parser.add_argument(
        "--disable-password",
        action="store_true",
        help="clear the user's password so only passkeys can sign in",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            print(f"error: no user {args.username!r}", file=sys.stderr)
            return 1
        if args.disable_password and user.password_hash:
            user.password_hash = None
            db.commit()
            print(f"password login disabled for {user.username}", file=sys.stderr)

        token = create_passkey_enroll_token(str(user.id), user.username, ttl_minutes=args.ttl)
        print(f"{settings.public_url.rstrip('/')}/passkeys/enroll?token={token}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
