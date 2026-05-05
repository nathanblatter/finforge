# CI/CD

- **Org:** github.com/nathanblatter
- **Runner:** Native macOS GitHub Actions runner on Mac Mini (launchd service at ~/actions-runner)
- **Deploy trigger:** Push to `main` branch
- **Deploy workflow:** `.github/workflows/deploy.yml` — pulls latest code in `/Users/nathanblatter/Desktop/finforge`, rebuilds Docker containers, and restarts
- **Secrets:** `.env` file + `secrets/` directory on host (both gitignored) — contains Plaid, Schwab, JWT, Cloudflare, and Anthropic credentials
- **Infrastructure:** Docker Compose (API + UI + cron + Cloudflare tunnel), shared Postgres from docker-services
