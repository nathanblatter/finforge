#!/usr/bin/env python3
"""
One-shot Schwab OAuth re-authentication for FinForge.

Run this whenever the 7-day refresh token window lapses
(cron logs show: invalid_grant / "Refresh token is invalid, expired or revoked").

Usage:
    python3 scripts/schwab_reauth.py

Steps it walks you through:
  1. Prints the Schwab authorize URL — open it, log in, approve.
  2. Schwab redirects your browser to SCHWAB_REDIRECT_URI with ?code=...
     (the page itself may not load — that's fine, just copy the URL).
  3. Paste the full redirect URL back here.
  4. Exchanges the code and writes secrets/schwab_tokens.json,
     preserving the existing account_hashes mapping.
"""

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def host_token_path(env_value: str) -> str:
    # The env var holds the container path (/secrets/...); map it to the host repo.
    if env_value.startswith("/secrets/"):
        return os.path.join(REPO_ROOT, "secrets", os.path.basename(env_value))
    return env_value


def main() -> None:
    env = load_env(os.path.join(REPO_ROOT, ".env"))
    client_id = env.get("SCHWAB_CLIENT_ID")
    client_secret = env.get("SCHWAB_CLIENT_SECRET")
    redirect_uri = env.get("SCHWAB_REDIRECT_URI")
    token_file = host_token_path(env.get("SCHWAB_TOKEN_FILE", "/secrets/schwab_tokens.json"))

    if not all([client_id, client_secret, redirect_uri]):
        sys.exit("Missing SCHWAB_CLIENT_ID / SCHWAB_CLIENT_SECRET / SCHWAB_REDIRECT_URI in .env")

    authorize = AUTHORIZE_URL + "?" + urllib.parse.urlencode(
        {"client_id": client_id, "redirect_uri": redirect_uri}
    )
    print("\n1. Open this URL in your browser and log in to Schwab:\n")
    print("   " + authorize + "\n")
    print("2. After approving, your browser lands on the redirect URI with ?code=...")
    print("   Copy the ENTIRE URL from the address bar (the page may show an error — ignore it).\n")

    redirect_url = input("3. Paste the full redirect URL here: ").strip()
    query = urllib.parse.urlparse(redirect_url).query
    code = urllib.parse.parse_qs(query).get("code", [None])[0]
    if not code:
        sys.exit("No ?code= parameter found in that URL. Re-run and paste the full redirect URL.")

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
    ).encode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Token exchange failed ({exc.code}): {exc.read().decode()[:300]}")

    expires_in = int(data.get("expires_in", 1800))
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    # Preserve account_hashes from the existing token file if present
    existing: dict = {}
    try:
        with open(token_file) as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    tokens = {
        **existing,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": expires_at,
    }
    tmp = token_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump(tokens, f, indent=2)
    os.replace(tmp, token_file)

    print(f"\nTokens saved to {token_file}")
    print("Now restart the cron container so it picks them up:")
    print("  docker compose -f " + os.path.join(REPO_ROOT, "docker-compose.yml") + " restart finforge-cron")


if __name__ == "__main__":
    main()
