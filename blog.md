# FinForge: How I Built My Own Finance App

### A self-hosted personal finance platform, built in six weeks on a Mac mini.

![Cover Image](cover.png)
<!-- Cover image idea: A clean, moody desk shot — Mac mini with a subtle power light,
a monitor in the background showing a dark-themed dashboard with financial charts/graphs,
soft ambient lighting. Think r/battlestations meets fintech. The focus should be on the
hardware and the screen, not on any specific data. -->

> **Excerpt:** I got tired of logging into four different apps and downloading bad PDFs to
> understand my own money. So I built FinForge — a self-hosted finance platform that pulls
> from my banks and brokerages into one dashboard, running on a Mac mini in my room.

---

## Why?

The short version: I got tired of logging into four different banking apps and downloading bad PDFs to figure out where my money was going.

I tried the usual suspects — Mint, YNAB, Copilot — none of them did what I actually wanted, and they all cost money. So about six weeks ago, I decided to just build the thing myself.

I'm an IS student with about two years of dev experience. This isn't a class project — it's something I actually use.

---

## What It Does

FinForge pulls in data from all my accounts automatically and puts it in one place.

```
┌─────────────────────────────────────────────────┐
│                   FinForge                       │
│                                                  │
│   ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│   │ Banking  │  │ Credit   │  │ Investments  │  │
│   │          │  │ Cards    │  │              │  │
│   └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│        │              │               │          │
│        └──────────────┼───────────────┘          │
│                       ▼                          │
│              ┌────────────────┐                  │
│              │  Unified View  │                  │
│              └────────────────┘                  │
└─────────────────────────────────────────────────┘
```

I'm pulling from **Wells Fargo**, **American Express**, and **Charles Schwab** — banking, credit cards, and investments all in one place. No spreadsheets, no PDFs, no switching between apps.

---

## The Stack

The whole thing runs on a **Mac mini M4** sitting on my desk, inside Docker Compose.

```
Frontend:   React + TypeScript (Vite) → Nginx
Backend:    FastAPI (Python)
Database:   PostgreSQL
ETL:        Python cron jobs
Tunnel:     Cloudflare Tunnel (cloudflared)
AI:         Claude API (server-side only)
Messaging:  NateBot (iMessage via REST API)
```

I went with FastAPI because it's fast to write and async out of the box. React + Vite because it's what I know and the dev experience is great. Postgres because it just works.

### How It's Hosted

Four containers running on the Mac mini:

```yaml
services:
  finforge-api:      # FastAPI backend
  finforge-ui:       # React app served by Nginx
  finforge-tunnel:   # Cloudflare Tunnel
  finforge-cron:     # Scheduled data pulls
```

I originally wanted to keep this Tailscale-only, but Plaid requires a publicly accessible domain with SSL. That forced my hand — I ended up using a **Cloudflare Tunnel** to expose the site. `cloudflared` runs as a container, creates an outbound connection to Cloudflare, and I get a real domain with automatic SSL. No port forwarding, no messing with my router.

Nginx sits in front of the React app, serves static files, and proxies `/api/` requests back to FastAPI.

> [!TIP]
> If you're running a homelab and need public access, Cloudflare Tunnel is worth looking into. Zero router config — just a container and a domain.

### Getting the Data In

This is where it gets interesting. I'm pulling from two totally different sources:

<details>
<summary><strong>Plaid</strong> — for banking (Wells Fargo + Amex)</summary>

Plaid handles checking accounts, credit cards, and transaction history. Setting it up was by far the hardest part of the whole project. The API is fine — it's everything around it. The SSL requirement, the webhook configuration, getting the token exchange working. It's a lot of yak-shaving, but once it's running, it just works.

</details>

<details>
<summary><strong>Schwab Trader API</strong> — for investments</summary>

OAuth-based API for my brokerage and Roth IRA. Gives me positions, market data, and balances. This is the part I'm most proud of — watching live stock market data flow into my dashboard and being able to track my **paycheck-to-investing pipeline** end to end.

</details>

Python cron jobs run on a schedule to pull fresh data from both sources and load it into Postgres.

---

## Security

I'm putting all my financial data in one place, so I take this seriously.

> [!IMPORTANT]
> No account numbers are stored in the database. Accounts are referenced by internal UUID and alias only.

- Secrets (Plaid tokens, Schwab OAuth creds) live in `.env`/secrets files, never in the database
- Claude API key is server-side only — the frontend doesn't know about it
- Cloudflare Tunnel means no ports are open on my home network
- Nginx enforces strict Content Security Policy headers

---

## What's Next

<details>
<summary><strong>Claude AI integration</strong></summary>

I'm adding Claude as a backend service so I can ask questions about my own data in plain English. Things like "how much did I spend on food this month?" or "what's my biggest category trend?" All server-side — the API key stays on the backend.

</details>

<details>
<summary><strong>NateBot — iMessage morning briefing</strong></summary>

An iMessage bot that sends me a daily snapshot every morning — balances, notable transactions, goal progress. Basically a financial briefing before I've had coffee.

</details>

<details>
<summary><strong>Goals</strong></summary>

Spending targets, savings goals, investment milestones. The part that turns data into decisions.

</details>

### Progress

- [x] Foundation — Docker Compose, Postgres, FastAPI skeleton
- [x] Data Ingestion — Plaid + Schwab ETL pipelines
- [x] Core API — REST endpoints
- [x] React UI — Dashboard, Spending, Investment panels
- [ ] Goals — Spending targets, savings goals, alerts
- [ ] Claude Integration — AI insights + chat
- [ ] NateBot — Morning briefing
- [ ] Hardening — Error handling, logging, backups

---

## The Hardest Part

Setting up Plaid. Easily.

The API documentation is good, but the requirement for a public domain with SSL cascaded into a bunch of infrastructure work I didn't plan for. It's what pushed the project from "homelab toy" to "actual deployed site." Worth it, but I definitely questioned my life choices at 2 AM trying to get token exchange working through a Cloudflare Tunnel.

## The Best Part

Seeing the paycheck-to-investment pipeline working end to end. Money comes in, gets tracked, gets invested — and I can see the whole flow in one place. That was the moment it went from "project" to "tool I actually rely on."

---

## What "Done" Looks Like

Being able to see a complete picture of my finances and make informed decisions from it. Being able to set goals on spending, saving, and investing. That's all I want. No social features, no gamification — just clarity.

---

<sub>Built with FastAPI, React, PostgreSQL, Plaid, Schwab Trader API, and Claude. Self-hosted on a Mac mini M4.</sub>
