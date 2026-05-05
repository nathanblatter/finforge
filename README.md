# FinForge

A self-hosted personal finance platform that aggregates banking and brokerage data into a unified dashboard with AI-powered insights.

## Overview

FinForge pulls transaction and investment data from multiple financial accounts via Plaid and the Schwab Trader API, normalizes it into a local PostgreSQL database, and presents it through a React dashboard. All data stays on your own hardware — no third-party cloud storage.

**Key features:**
- Unified view across checking, credit cards, brokerage, and retirement accounts
- Automated nightly data sync via Plaid and Schwab APIs
- AI financial coach powered by Claude (goal tracking, spending insights, accountability)
- Portfolio analysis with drawdown modeling
- Spending categorization with fixed/variable/discretionary tiers
- Monthly PDF financial reports
- Watchlists with real-time market data and options chains
- iMessage integration via NateBot for on-the-go queries

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  finforge-ui│     │ finforge-api│     │finforge-cron│
│  React/TS   │────▶│  FastAPI    │◀────│  Scheduler  │
│  Port 3003  │     │  Port 8001  │     │             │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                    │
                    ┌──────▼──────┐      ┌──────▼──────┐
                    │  PostgreSQL │      │  Plaid API  │
                    │  (shared)   │      │  Schwab API │
                    └─────────────┘      └─────────────┘
```

| Service | Description |
|---------|-------------|
| `finforge-api` | FastAPI backend — accounts, spending, investments, goals, AI chat |
| `finforge-ui` | React + TypeScript + Tailwind dashboard |
| `finforge-cron` | Python scheduler — nightly Plaid/Schwab sync, market data, alerts |
| `finforge-tunnel` | Cloudflare tunnel for secure external access |

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, Alembic
- **Frontend:** React 18, TypeScript, TanStack Query, Recharts, Tailwind CSS
- **Data:** PostgreSQL 17, Plaid API, Schwab Trader API
- **AI:** Claude API (Anthropic) for financial insights and chat
- **Infra:** Docker Compose, Cloudflare Tunnels, GitHub Actions (self-hosted runner)

## Setup

1. **Configure environment**
   ```bash
   cp .env.example .env
   # Fill in API keys, database URL, and tunnel token
   ```

2. **Create the database**
   ```sql
   CREATE DATABASE finforge;
   ```

3. **Run migrations**
   ```bash
   docker compose run --rm finforge-api alembic upgrade head
   ```

4. **Start services**
   ```bash
   docker compose up -d
   ```

5. **Verify**
   ```bash
   curl http://localhost:8001/api/v1/health -H "X-API-Key: <your-key>"
   ```

## Development

The API directory is volume-mounted for hot reload via uvicorn `--reload`. Frontend dev server:

```bash
cd ui && npm install && npm run dev
```

## Migrations

```bash
# Generate migration after model changes
docker compose run --rm finforge-api alembic revision --autogenerate -m "description"

# Apply
docker compose run --rm finforge-api alembic upgrade head
```

## Deployment

Pushes to `main` trigger automatic deployment via GitHub Actions on a self-hosted runner.
