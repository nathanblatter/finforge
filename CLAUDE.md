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
