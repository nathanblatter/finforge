# Vision

**Financial data reliably aggregated to motivate me to save and invest my money.**

Every feature must serve reliable aggregation or savings/investing motivation — kill anything that doesn't. Data trust (correct numbers, live syncs, alerts that actually fire) outranks new features.

# CI/CD

- **Org:** github.com/nathanblatter
- **Runner:** Native macOS GitHub Actions runner on Mac Mini (launchd service at ~/actions-runner)
- **Deploy trigger:** Push to `main` branch
- **Deploy workflow:** `.github/workflows/deploy.yml` — pulls latest code in `/Users/nathanblatter/dev/finforge`, rebuilds Docker containers, and restarts
- **Secrets:** `.env` file + `secrets/` directory on host (both gitignored) — contains Plaid, Schwab, JWT, Cloudflare, and Anthropic credentials
- **Infrastructure:** Docker Compose (API + UI + cron + Cloudflare tunnel), shared Postgres from docker-services

# Public MCP connector (Claude on the phone)

`finforge.nathanblatter.com/mcp` is served by the `finforge-mcp-public` container (same image
as the tailnet `finforge-mcp`, same read-only tools). It is an OAuth protected resource: every
request needs a bearer token from Squawk, the auth service (https://squawk.nathanblatter.com), which Nathan
approves per connector in its admin console with his passkey. The UI nginx forwards only `/mcp`
and `/.well-known/oauth-protected-resource/mcp` to it; nothing else on the hostname changed.
Config is plain env in docker-compose.yml (`AUTH_ISSUER`, `AUTH_AUDIENCE` = FinForge's service
id in Squawk, `AUTH_RESOURCE`). Tests: `cd mcp && python -m pytest tests` (CI job test-mcp).

# UI sign-in (Squawk)

The web UI signs in **only** through Squawk (https://squawk.nathanblatter.com); the native
password / TOTP-MFA / WebAuthn login was removed in Oct 2026. FinForge is an invite-only user
pool there (service `svc_zlezt62ewdgohvyi`, login_url `/login`, rp_id `finforge.nathanblatter.com`)
with a public PKCE OAuth client whose redirect_uri is `/login/callback`.

Flow: `/login` → "Sign in with Squawk" (PKCE generated in the browser, verifier in
sessionStorage) → Squawk `/oauth/authorize` → browser lands back on `/login?login_challenge=`
→ "Sign in as owner" (Nathan's Squawk passkey; also "Use an account passkey" / "Email me a code"
for provisioned accounts) via the API proxies `/api/v1/auth/squawk/{owner,passkey,email}/{begin,finish}`
→ Squawk redirects to `/login/callback?code&state` → `POST /auth/squawk/exchange {code, code_verifier}`
→ the API exchanges + verifies the Squawk token (ES256 JWKS, aud = service id) and mints FinForge's
own HS256 session JWT, so every `require_auth` site is unchanged. Only `sub=owner` is mapped (to
the user named by `SQUAWK_OWNER_USERNAME`); `usr:…` subjects get 403 because FinForge has no
email column. Approving the Claude connector while logged in also lands on
`/login?login_challenge=` — use "Sign in as owner" there too (the LoginRoute does not redirect
away when a challenge is present).

Env (all in `.env`; `docker compose` passes it to the api via `env_file: .env`, so new vars need
no compose change): `SQUAWK_ISSUER`, `SQUAWK_SERVICE_ID`, `SQUAWK_CREDENTIAL` (service
credential), `SQUAWK_CLIENT_ID`, `SQUAWK_RESOURCE`, `SQUAWK_OWNER_USERNAME` (default `nathan`).
Empty `SQUAWK_ISSUER` (local dev) = disabled: `GET /auth/squawk/config` says `enabled: false`,
the login page shows "Squawk is not configured", and there is no way to sign in. That is
intentional — there is **no password fallback**; Squawk recovery codes are the break-glass.
Code: `api/squawk.py` (client + verifier), `api/routers/auth.py`, `ui/src/api/squawk.ts`,
`ui/src/pages/LoginPage.tsx`, `ui/src/pages/LoginCallbackPage.tsx`. Tests:
`api/tests/test_squawk_auth.py` (Squawk mocked at the httpx layer).
