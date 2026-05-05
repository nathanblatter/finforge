FINFORGE
Personal Finance Platform
 
Product Requirements Document  |  v1.0
 
Document Metadata
 
Owner: Nathan Blatter
Version: 1.0 — Initial PRD
Date: March 2026
Status: Draft — Ready for Development
Target Infrastructure: Mac mini M4 homelab  |  Docker  |  Tailscale private network
 
1. Executive Summary

FinForge is a self-hosted personal finance platform built for Nathan Blatter's Mac mini homelab. It aggregates financial data across all accounts — Wells Fargo checking and credit card, American Express credit card, Schwab individual brokerage, and Schwab Roth IRA — and presents it in a unified dashboard that promotes a save-and-invest mental model.
 
The platform is architected around three principles:
• Data ownership: all financial data is stored locally in a PostgreSQL Docker instance, de-identified (no account numbers, card numbers, or credentials ever persisted)
• Automation-first: nightly Python cron jobs pull data from Plaid (Wells Fargo + Amex) and the Schwab Trader API, normalize it, and load it into Postgres with no manual intervention
• Extensibility: a clean REST API exposes aggregated financial data to other homelab services, most notably NateBot — Nathan's iMessage Swift daemon — without exposing any sensitive account information
 
A React + TypeScript frontend with Claude AI integration provides goal-setting, accountability coaching, and proactive financial insights. The system is accessible exclusively over Tailscale, with no public-facing surface for the UI.
 
2. Financial Context & Account Model

This section defines how FinForge understands and categorizes Nathan's financial life. These distinctions drive UI design, goal frameworks, and data aggregation logic.
 
2.1 Account Inventory
Account
Role in System
WF Checking
Primary payment hub. Fixed large expenses: rent, tuition. Source of truth for cash liquidity.
WF Credit Card
Day-to-day spending card. Used for any merchant that accepts CC without a fee surcharge.
Amex Credit Card
Day-to-day spending card. Used interchangeably with WF CC based on rewards / acceptance.
Schwab Individual Brokerage
Primary savings vehicle. Mix of cash and lower-risk positions (Mag 7, S&P index). Treated as a savings account balance, not a trading account.
Schwab Roth IRA
Long-term retirement account. Tracked separately. Contributions vs. growth reported independently. Mentally untouchable — not counted as accessible savings.
 
2.2 Spending Model
FinForge distinguishes three spending tiers:
 
Tier
Category
Source Account(s)
Fixed
Rent, tuition — recurring, non-discretionary
WF Checking
Variable CC
All other day-to-day purchases
WF Credit Card + Amex
Transfers / Investments
Contributions to brokerage or IRA
WF Checking → Schwab
 
The CC spending pool (WF CC + Amex) is tracked as a combined discretionary spend total, but both cards are displayed individually for transaction-level detail. Rent and tuition are isolated as fixed expenses and excluded from discretionary spend calculations so they do not inflate spending goal thresholds.
 
2.3 Savings & Investment Model
The Schwab individual brokerage is the primary savings metric. Because it holds a mix of cash and invested positions, FinForge treats the total portfolio value (cash + holdings market value) as the "savings balance." This is what savings goals are measured against.
 
The Roth IRA is tracked separately and surfaces in the net worth calculation and a dedicated IRA panel, but is visually and logically separated from the savings balance. It shows: current balance, annual contribution amount, annual contribution limit ($7,000 for 2026), and growth attribution (contributions vs. market gains).
 
3. Goals & Success Criteria

3.1 User Goals
• Maintain a single source of truth for all financial data without logging into multiple apps
• Understand discretionary spending patterns across both credit cards in real time
• Track progress toward customizable savings and investment goals
• Receive proactive accountability — via the web UI and NateBot iMessage — without having to check in manually
• Have a REST API that allows NateBot and future services to consume financial summaries safely
 
3.2 Non-Goals (Out of Scope v1)
• Bill pay or any write operations to financial accounts
• Multi-user support
• Mobile app (Tailscale access on mobile browser is sufficient for v1)
• Tax optimization or tax document management
• Crypto or alternative asset tracking
• ML-powered anomaly detection (v2 stretch goal, infrastructure is prepared for it)
 
4. System Architecture

4.1 High-Level Overview
 
Infrastructure Stack
 
Host: Mac mini M4 (16GB RAM) — existing homelab
Containerization: Docker Compose — all services containerized
Database: PostgreSQL (existing Docker instance)
Backend: Python (FastAPI) — chosen for ML readiness and async support
Frontend: React + TypeScript (Vite)
Cron / ETL: Python APScheduler or system cron — nightly data ingestion
Networking: Tailscale — UI and API accessible only on tailnet
Secrets: Docker secrets or .env file — never committed to version control
 
4.2 Service Topology
 
Service
Description
finforge-api
FastAPI Python backend. Serves REST API, handles business logic, exposes NateBot endpoints.
finforge-ui
React + TypeScript frontend. Served via Nginx container on the Tailscale interface.
finforge-cron
Python cron service. Runs nightly data ingestion from Plaid and Schwab APIs. Separate container for isolation.
postgres
Existing PostgreSQL Docker instance. FinForge uses a dedicated database within the existing instance.
pgadmin
Existing pgAdmin instance. FinForge DB accessible through it.
 
4.3 Data Flow
 
1. Nightly cron (2:00 AM) triggers Plaid sync for WF Checking, WF CC, and Amex CC
2. Nightly cron (2:05 AM) triggers Schwab API sync for Individual Brokerage and Roth IRA
3. ETL layer normalizes, categorizes, and de-identifies all data before writing to Postgres
4. FastAPI backend reads from Postgres and serves data to React UI and NateBot REST endpoints
5. React UI fetches data from FastAPI and renders dashboards, goals, and Claude-powered insights
6. NateBot polls or webhooks the FinForge REST API for morning briefing data and alerts
 
4.4 Backend: Why FastAPI + Python
• Async-native: FastAPI handles concurrent requests efficiently without callback hell
• ML-ready: when v2 ML features are added (spending anomaly detection, goal trajectory modeling), scikit-learn, pandas, and numpy are first-class citizens
• Type-safe: Pydantic models provide schema validation that mirrors TypeScript interfaces on the frontend
• Auto-docs: FastAPI generates OpenAPI docs automatically — useful for NateBot integration development
• Cron consistency: the nightly ETL jobs are also Python, so the entire backend is one language with shared utility libraries
 
5. Data Model

5.1 De-identification Policy
 
CRITICAL: What is NEVER stored in Postgres
 
• Full account numbers or card numbers
• Routing numbers
• Plaid access tokens or item IDs (stored only in encrypted .env / secrets)
• Schwab OAuth tokens (stored only in encrypted token file, not in DB)
• SSN or any identity document data
• Bank login credentials of any kind
 
Accounts are referenced by an internal UUID assigned by FinForge. A human-readable alias (e.g. "WF Checking", "Amex") is stored alongside the UUID. The last 4 digits of an account may optionally be stored for display purposes only.
 
5.2 Core Tables
 
Table
Purpose
accounts
Internal account registry. UUID, alias, type (checking/cc/brokerage/ira), institution, last4 (optional).
transactions
Normalized transaction records. date, amount, merchant_name, category, subcategory, account_uuid, is_pending, is_fixed_expense.
balances
Daily balance snapshots per account. account_uuid, balance_date, balance_amount, balance_type (cash/portfolio_value).
holdings
Brokerage/IRA position snapshots. account_uuid, snapshot_date, symbol, quantity, market_value, cost_basis.
goals
User-defined goals. See Section 6.3 for schema detail.
goal_snapshots
Daily progress snapshots against each goal. goal_id, snapshot_date, current_value, target_value, pct_complete.
claude_insights
Cached Claude-generated insights. insight_date, insight_type, content, expires_at.
natebot_events
Log of data sent to NateBot. timestamp, event_type, payload_hash (no sensitive data).
 
5.3 Transaction Categorization
Transactions ingested from Plaid carry Plaid's native category tags. FinForge maps these to an internal category taxonomy optimized for Nathan's financial model:
 
Internal Category
Subcategories
Notes
Housing
Rent
Fixed expense — excluded from discretionary total
Education
Tuition, fees
Fixed expense — excluded from discretionary total
Food & Drink
Restaurants, coffee, groceries
Discretionary
Shopping
Clothing, electronics, general retail
Discretionary
Transport
Gas, rideshare, parking
Discretionary
Entertainment
Subscriptions, events
Discretionary
Health
Gym, medical, pharmacy
Discretionary
Investment Transfer
Brokerage contributions
Tracked separately as savings activity
Other
Uncategorized
User can re-categorize in UI
 
6. Feature Specifications

6.1 Dashboard — Net Worth Overview
The primary landing screen. Designed to reinforce a save-and-invest mental model at a glance.
 
Key Metrics (top of page)
• Net Worth: sum of WF Checking balance + Schwab Brokerage value + Schwab Roth IRA value — CC balances owed
• Savings Balance: Schwab Brokerage total portfolio value (cash + holdings). Labeled clearly as "Savings (Brokerage)" to reinforce the mental model
• Liquid Cash: WF Checking balance
• Outstanding CC Balance: combined WF CC + Amex balance currently owed
 
Net Worth Trend Chart
• Line chart: rolling 12-month net worth history, plotted from daily balance snapshots
• Stacked area variant showing breakdown: Cash, Brokerage, Roth IRA, CC Liability
 
Account Cards
• One card per account, showing current balance, last updated timestamp, and trend arrow (vs. 30 days ago)
• Roth IRA card is visually distinct (muted / locked appearance) with a label: "Retirement — Long-term"
 
6.2 Spending Dashboard
Discretionary Spend
• Monthly spend total across WF CC + Amex, excluding fixed expenses (rent, tuition)
• Category breakdown: donut chart with drill-down to transaction list per category
• Card-level split: how much was charged to WF CC vs Amex this month
• Month-over-month comparison bar chart
 
Fixed Expenses Panel
• Rent and tuition displayed separately — amounts, due dates if configured, and YTD total
• Not counted in discretionary spend calculations
 
Transaction Feed
• Chronological list of all transactions across all accounts
• Filterable by account, category, date range, amount range
• Inline re-categorization — user can correct Plaid's category assignments
• Pending transactions shown with distinct visual treatment
 
6.3 Goal Framework
Goals are the core accountability mechanism. The framework supports fully customizable goal types rather than prescribing fixed templates.
 
Goal Schema
Field
Description
goal_id
UUID
name
User-defined label (e.g. "Hit $25k savings by August")
goal_type
Enum: balance_target | contribution_rate | spend_limit | portfolio_growth | custom
metric_source
Which account(s) or category feed this goal
target_value
Numeric target (dollar amount, percentage, etc.)
target_date
Optional deadline
direction
Enum: increase | decrease | maintain
cadence
How often progress is evaluated: daily | weekly | monthly
alert_threshold
Percentage off-track that triggers an alert (e.g. 10%)
natebot_enabled
Boolean — include this goal in NateBot briefings
status
active | paused | completed | failed
 
Built-in Goal Templates (pre-configured starting points)
• Balance Target: "Reach $X in my brokerage by [date]"
• Monthly Contribution: "Contribute at least $X/month to brokerage"
• Spend Limit: "Keep discretionary CC spend under $X/month"
• Category Limit: "Spend less than $X on [category] this month"
• IRA Contribution: "Max out Roth IRA by end of year ($7,000)"
• Portfolio Growth: "Grow brokerage by X% over Y months"
• Custom: user defines the metric, source, and target freely
 
Goal Progress UI
• Progress bar with current vs. target value
• Projected completion date based on current trajectory
• Historical progress chart (daily snapshots)
• Status badge: On Track / At Risk / Off Track / Completed
 
6.4 Accountability & Alerts
In-App Alerts
• Banner notification when any goal crosses the alert_threshold
• Alerts persist until dismissed
• Alert log with history
 
NateBot iMessage Integration
• Morning briefing line item: each goal with natebot_enabled = true is summarized
• Off-track alerts: NateBot sends an iMessage when a goal goes off-track
• Weekly spending summary: total discretionary spend this week vs. last week
• All NateBot payloads sourced from the FinForge REST API — no sensitive data in payload
 
6.5 Claude AI Integration
Proactive Insights (Dashboard)
• Daily Claude-generated insight surfaced on the dashboard
• Examples: "Your food & drink spend is up 34% this month vs. last — mostly Uber Eats on weekends." or "You're on pace to hit your $25k savings goal 3 weeks early."
• Insights cached in claude_insights table and refreshed nightly alongside data sync
• Insight types: spending_pattern | goal_trajectory | savings_opportunity | anomaly
 
Chat Interface
• Embedded Claude chat panel in the UI — asks questions, gets financial answers
• Context window includes: current balances, recent transactions (de-identified), active goals, and goal progress
• Example queries: "Am I on track to max my Roth this year?" or "How does my October spending compare to September?" or "What categories should I cut to hit my savings goal faster?"
• Chat history is session-only — not persisted to DB
• Claude API called server-side from FastAPI — API key never exposed to frontend
 
6.6 Investment Panel
Brokerage View
• Total portfolio value, cash position, invested position
• Holdings table: symbol, quantity, current price, market value, cost basis, unrealized gain/loss, % of portfolio
• Portfolio allocation pie chart
• 30-day, 90-day, 1-year performance chart
 
Roth IRA View
• Current balance with contribution vs. growth breakdown
• Annual contribution tracker: amount contributed this year vs. $7,000 limit
• Contribution history by year
• Visually separated from brokerage — distinct color scheme and "Retirement" label
• Included in net worth calculation but excluded from savings balance metric
 
7. REST API Specification

7.1 Design Principles
• All endpoints return JSON
• No sensitive account data (numbers, credentials) in any response
• Tailscale-only access — no public exposure
• Authentication: API key via request header (X-API-Key) for NateBot and service-to-service calls
• FastAPI auto-generates OpenAPI docs at /docs
 
7.2 Endpoint Reference
 
Method + Path
Description
NateBot Use
GET /api/v1/summary
Net worth, savings balance, liquid cash, total CC owed. Snapshot of current financial state.
Morning briefing
GET /api/v1/balances
Current balance per account (alias only, no account numbers)
Balance check
GET /api/v1/spending/monthly
Discretionary spend this month, by category. Fixed expenses excluded.
Weekly summary
GET /api/v1/spending/transactions
Recent transactions. Filterable by days, category, account alias.
Spend query
GET /api/v1/goals
All active goals with current progress and status.
Goal briefing
GET /api/v1/goals/{id}
Single goal detail with progress history.
-
GET /api/v1/investments/brokerage
Brokerage portfolio value, holdings summary, performance.
-
GET /api/v1/investments/ira
Roth IRA balance, contributions YTD, growth.
-
GET /api/v1/insights/latest
Latest Claude-generated insight(s) by type.
Insight delivery
GET /api/v1/alerts
Active unacknowledged goal alerts.
Alert delivery
POST /api/v1/alerts/{id}/acknowledge
Mark an alert as acknowledged.
-
GET /api/v1/health
Service health check. Returns sync status and last successful run times.
Uptime monitoring
 
7.3 NateBot Integration Pattern
NateBot polls GET /api/v1/summary and GET /api/v1/goals each morning as part of its existing morning briefing routine. It also subscribes to GET /api/v1/alerts on a more frequent cadence (e.g. every 4 hours) to catch off-track goal notifications. The FinForge API is registered as a service in NateBot's JSON config. Authentication uses a static API key stored in NateBot's environment.
 
8. Data Ingestion (Cron / ETL)

8.1 Plaid Integration (WF + Amex)
• One-time setup: Plaid Link flow run locally to connect WF Checking, WF CC, and Amex CC. Plaid access tokens stored encrypted in secrets file, never in DB.
• Nightly sync: Python script calls /transactions/sync for each Plaid Item, processes added/modified/removed transaction deltas
• Balance sync: /accounts/balance/get called nightly for current balance snapshots
• Amex MFA re-auth: if Plaid returns ITEM_LOGIN_REQUIRED, an alert is written to DB and surfaced in UI + NateBot
• Idempotency: transactions are upserted by Plaid transaction_id — duplicate runs are safe
 
8.2 Schwab API Integration
• OAuth setup: one-time browser auth flow following Schwab Individual Developer process. Token stored in encrypted file on Mac mini.
• Token refresh: access token refreshed every 25 minutes automatically. Refresh token (7-day) is rolled forward on every nightly run — service downtime > 7 days triggers a re-auth alert.
• Nightly sync: account balances and positions fetched via /accounts and /accounts/{accountHash}/positions endpoints
• Transaction history: /accounts/{accountHash}/orders used for investment activity
• Re-auth alert: if Schwab returns invalid_client (expired refresh token), alert is written to DB and sent via NateBot
 
8.3 ETL De-identification Steps
7. Receive raw API response from Plaid or Schwab
8. Strip all fields containing account numbers, routing numbers, or credentials
9. Map institution account ID to internal FinForge UUID (mapping stored only in secrets, not in DB)
10. Normalize transaction fields to FinForge schema (date, amount, merchant, category)
11. Apply category mapping (Plaid category → FinForge internal category)
12. Flag fixed expenses (rent, tuition) via merchant name matching and amount thresholds
13. Write to Postgres via upsert
 
8.4 Cron Schedule
Job
Schedule
plaid_sync
Daily at 2:00 AM
schwab_sync
Daily at 2:05 AM
generate_goal_snapshots
Daily at 2:30 AM (after data sync completes)
generate_claude_insights
Daily at 3:00 AM
check_goal_alerts
Every 4 hours
health_check
Every 15 minutes
 
9. Security Model

Concern
Mitigation
Credential storage
Plaid tokens and Schwab OAuth tokens stored in encrypted secrets file on Mac mini. Never written to DB or version control.
Network exposure
UI and API bound to Tailscale interface only. Not reachable from public internet.
API authentication
X-API-Key header required for all API requests. Key stored in NateBot environment, not in code.
Sensitive data in DB
ETL layer enforces de-identification before any write. No account numbers, card numbers, or tokens in Postgres.
Claude API key
Stored in FastAPI environment only. Never sent to frontend.
Version control
All secrets and .env files in .gitignore. Docker secrets used where possible.
DB access
Postgres accessible on Docker internal network only. pgAdmin accessible via existing Tailscale setup.
 
10. Development Milestones

 
Phase
Deliverables
Est. Effort
Phase 1: Foundation
Docker Compose setup, Postgres schema, FastAPI skeleton, health endpoint, secrets management
1 week
Phase 2: Data Ingestion
Plaid integration (WF + Amex), Schwab API integration, nightly cron, ETL de-identification pipeline
2 weeks
Phase 3: Core API
All REST endpoints, Pydantic schemas, OpenAPI docs, NateBot API key auth
1 week
Phase 4: React UI
Vite + React + TS scaffold, Dashboard, Spending view, Investment panel, Account cards
2 weeks
Phase 5: Goals
Goal CRUD, goal framework, progress tracking, alert engine, goal dashboard
1.5 weeks
Phase 6: Claude
Dashboard insights, chat interface, server-side Claude API integration, insight caching
1 week
Phase 7: NateBot
NateBot service config, morning briefing integration, alert iMessage delivery, end-to-end testing
0.5 weeks
Phase 8: Hardening
Error handling, re-auth alert flows, logging, DB backup strategy, README
1 week
 
11. Future Considerations (v2)

• ML anomaly detection: flag unusual spending transactions using a local model trained on historical data. Python + scikit-learn already available in the backend.
• Spending forecasting: predict end-of-month spend per category based on pace-to-date
• Contribution optimizer: suggest optimal monthly transfer to brokerage based on cash flow and goal targets
• Schwab watchlist integration: surface watched symbols alongside portfolio in investment panel
• CSV export: export transactions or balance history to CSV for tax prep or external analysis
• CI/CD: GitHub Actions self-hosted runner (already available in homelab) for automated deploys on push to main
 
 
FinForge  |  Nathan Blatter  |  v1.0  |  March 2026  |  Confidential
 