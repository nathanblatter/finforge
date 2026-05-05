# PRD: FinForge × NateBot Integration

## Overview

Local-only notification API for FinForge that NateBot polls and consumes, enabling iMessage delivery of financial alerts, daily briefings, portfolio risk warnings, and goal updates. Both services run on the same Mac Mini — communication is `localhost` HTTP only.

## Status

**Phase 1 (FinForge API): COMPLETE** — All endpoints built, deployed, and tested.

Phase 2 (NateBot Swift integration): Not started.

## Architecture

```
┌─────────────────┐         localhost:8001          ┌──────────────────┐
│   FinForge API   │◄──────────────────────────────│    NateBot        │
│   (Docker)       │    GET /api/v1/natebot/*       │    (launchd)      │
│   port 8001      │────────────────────────────────►│    port 47382     │
│                  │    Formatted iMessage strings   │                  │
└─────────────────┘                                 └──────────────────┘
                                                           │
                                                    osascript/Messages
                                                           │
                                                           ▼
                                                     iMessage to
                                                  nathan.blatter@yahoo.com
```

**Flow:** FinForge cron jobs produce notifications into a `natebot_queue` table. NateBot polls `GET /natebot/pending` on an interval, receives pre-formatted iMessage strings, and sends them via `ReplyAction.send()`. NateBot can also fetch on-demand data (portfolio, predictions, goals) when the user texts a command.

---

## Phase 1: FinForge API (COMPLETE)

### Files Created/Modified

| File | Change |
|------|--------|
| `api/routers/natebot_imessage.py` | **New** — All 7 iMessage endpoints |
| `api/models/db_models.py` | Added `NatebotQueue` model |
| `api/routers/__init__.py` | Registered `natebot_imessage_router` |
| `api/main.py` | Included `natebot_imessage_router` |
| `cron/db.py` | Added `NatebotQueueRow` mirror model |
| `cron/notify.py` | **New** — `queue_notification()` helper for cron jobs |
| `cron/goal_engine.py` | Wired goal alerts → `natebot_queue` |
| `cron/integrations/portfolio_analysis.py` | Wired TLH + drift alerts → `natebot_queue` |
| `cron/integrations/drawdown_model.py` | Post-training predictions → `natebot_queue` for VERY_HIGH risk |
| Database | `natebot_queue` table created |

### Endpoints (Live)

All endpoints are at `localhost:8001/api/v1/natebot/`, authenticated via `X-API-Key` header.

Every endpoint returns `{"text": "...", "generated_at": "..."}` — the `text` field is a pre-formatted iMessage string ready for `ReplyAction.send()` with no further formatting needed by NateBot.

#### 1. `GET /natebot/pending`

NateBot polls this every 60 seconds. Returns queued notification messages, then marks them `delivered=true` so they won't appear again.

```json
{
  "messages": [
    {
      "id": "uuid",
      "priority": "normal",
      "category": "goal_alert",
      "text": "⚠️ Goal 'Savings Target' is off track (42.1%). Current: $21,050 / Target: $50,000.",
      "created_at": "2026-04-19T02:30:00Z"
    }
  ],
  "count": 1
}
```

**Active notification producers:**

| Producer | Category | Trigger |
|----------|----------|---------|
| `goal_engine.py` `run_check_goal_alerts()` | `goal_alert` | When a new GoalAlert is created (off_track, at_risk, completed) |
| `portfolio_analysis.py` | `tlh_signal` | When any holding has `unrealized_loss < -$100` |
| `portfolio_analysis.py` | `portfolio_drift` | When any holding drifts >5% from target allocation |
| `drawdown_model.py` post-training | `drawdown_warning` | When any held position has >60% drawdown probability |

#### 2. `GET /natebot/imessage/briefing`

Full financial snapshot. Includes net worth, account balances, portfolio risk metrics (HHI, weighted volatility), active goals with progress, unacknowledged alert count, and latest Claude insight.

```
💰 FinForge — Sunday, Apr 19

Net Worth: $3,258.36
Brokerage: $1,983.35
Roth IRA: $1,275.01

📊 Portfolio Risk
HHI: 2096 | Vol: 37.0%

🎯 Goals
🔴 Net Worth Target — 32.6% (Off Track)
🔴 Grow Schwab Roth IRA — 51.0% (Off Track)

💡 [latest Claude insight excerpt]
```

#### 3. `GET /natebot/imessage/portfolio`

Holdings table with risk metrics from the latest portfolio analysis. Falls back to raw holdings if no analysis exists yet.

```
📊 Portfolio — $1,746.87

TXN $459.64 (26.3%) — vol 35% — β1.17
AVGO $406.54 (23.3%) — vol 43% — β1.90
GOOGL $341.68 (19.6%) — vol 29% — β1.18
GOOG $339.40 (19.4%) — vol 28% — β1.15
ORCL $175.06 (10.0%) — vol 62% — β1.63 — ⚠️TLH
GME $24.55 (1.4%) — vol 44% — β0.82

HHI: 2096 | WeightedVol: 37.0%
```

#### 4. `GET /natebot/imessage/predict/{symbol}`

On-demand drawdown prediction. Fetches 1-year price history from Schwab, computes features, runs the GradientBoosting model, caches the result, and returns formatted text. Works for any symbol — holdings, watchlist, or arbitrary tickers.

```
🔮 AAPL Drawdown Risk

🟡 34.2% chance of >5% drop in 30 days
Risk Level: MODERATE

Model AUC: 0.847
```

**Requires:** Trained model at `/secrets/drawdown_model.pkl`. Returns "Model not trained yet" message if missing.

#### 5. `GET /natebot/imessage/goals`

All active/paused financial goals with current value, target, percentage, and status badge.

```
🎯 Financial Goals

🔴 Net Worth Target — $3,258.36 / $10,000.00 (32.6%) Off Track
🔴 Grow Schwab Roth IRA — $1,275.01 / $2,500.00 (51.0%) Off Track
```

#### 6. `GET /natebot/imessage/watchlist`

All user watchlists with cached quotes (price, change, change %).

```
👁 Tech

AAPL $270.60 (+1.23, +0.46%)
MSFT $425.30 (-2.10, -0.49%)
GOOGL $340.55 (+3.82, +1.13%)
```

#### 7. `POST /natebot/imessage/chat`

Forwards a finance question to Claude with full financial context (balances, holdings, goals, watchlists, portfolio analysis). Response capped at 500 tokens with instruction to keep under 1500 characters for iMessage.

**Request:** `{"message": "how's my portfolio doing?"}`

**Response:** `{"text": "Your portfolio is worth $1,746...", "generated_at": "..."}`

Uses the same `_build_chat_context()` as the web chat, which includes: account balances, holdings with P&L, spending by category, active goals, watchlists with quotes, and portfolio analysis metrics.

### Notification Queue Schema

Table: `natebot_queue`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| priority | VARCHAR(10) | `urgent`, `normal`, `low` |
| category | VARCHAR(50) | Indexed. One of: `goal_alert`, `tlh_signal`, `drawdown_warning`, `portfolio_drift` |
| text | TEXT | Pre-formatted iMessage string |
| delivered | BOOLEAN | Default false. Indexed. Set true on `GET /pending` |
| delivered_at | TIMESTAMPTZ | When NateBot picked it up |
| created_at | TIMESTAMPTZ | Indexed |

Helper: `cron/notify.py` provides `queue_notification(category, text, priority)` which handles message splitting at 1600 chars (iMessage soft limit).

---

## Phase 2: NateBot Integration (TODO)

### New File: `FinForgeAction.swift`

Location: `/Users/nathanblatter/Desktop/natebot/natebot/Actions/FinForgeAction.swift`

```swift
class FinForgeAction {
    let baseURL: String  // "http://localhost:8001/api/v1/natebot"
    let apiKey: String
    let reply: ReplyAction
    let log: ActivityLog

    init(config: FinForgeConfig, reply: ReplyAction, log: ActivityLog)

    // Poll pending notifications — called by ProactiveMonitor every 60s
    func pollPending(completion: @escaping () -> Void)

    // On-demand fetches — called by CommandRouter/NLPRouter
    func briefing(completion: @escaping (String) -> Void)
    func portfolio(completion: @escaping (String) -> Void)
    func predict(symbol: String, completion: @escaping (String) -> Void)
    func goals(completion: @escaping (String) -> Void)
    func watchlist(completion: @escaping (String) -> Void)
    func chat(message: String, completion: @escaping (String) -> Void)
}
```

**Implementation pattern:** Follow the existing `StatusAction.swift` HTTP request pattern:
1. Build `URLRequest` to `baseURL + path`
2. Set `X-API-Key` header
3. For `POST /imessage/chat`: set `Content-Type: application/json` and body
4. Use `URLSession.shared.dataTask`
5. Parse response JSON, extract `text` field
6. Call `reply.send(text)` for on-demand, or return via completion
7. For `pollPending`: iterate `messages` array, call `reply.send()` for each, log to `ActivityLog`

### Config Addition

Add to `Config.swift`:

```swift
struct FinForgeConfig: Codable {
    let enabled: Bool
    let apiUrl: String      // "http://localhost:8001/api/v1"
    let apiKey: String
    let pollIntervalSeconds: Int  // 60

    enum CodingKeys: String, CodingKey {
        case enabled
        case apiUrl = "api_url"
        case apiKey = "api_key"
        case pollIntervalSeconds = "poll_interval_seconds"
    }
}
```

Add to `Config` struct: `let finforge: FinForgeConfig?`

Add to `natebot.json`:

```json
{
  "finforge": {
    "enabled": true,
    "api_url": "http://localhost:8001/api/v1",
    "api_key": "<same API_KEY as in finforge .env>",
    "poll_interval_seconds": 60
  }
}
```

### New Slash Commands

Add to `CommandRouter.swift` in the `route()` method:

| Command | Action |
|---------|--------|
| `/finance` | `finforgeAction.briefing { reply.send($0) }` |
| `/portfolio` or `/stocks` | `finforgeAction.portfolio { reply.send($0) }` |
| `/predict [SYMBOL]` | `finforgeAction.predict(symbol:) { reply.send($0) }` |
| `/fingoals` | `finforgeAction.goals { reply.send($0) }` |
| `/watchlist` | `finforgeAction.watchlist { reply.send($0) }` |

### NLP Router Update

Add to `NLPRouter.swift` system prompt (the action list Claude uses to route):

```
- "finforge_briefing" — user wants a financial summary, asks about money/finances/net worth
- "finforge_portfolio" — user asks about stocks, holdings, portfolio, investments
- "finforge_predict" — user asks about risk or prediction for a specific ticker (params: {"symbol": "AAPL"})
- "finforge_goals" — user asks about financial goals, savings progress
- "finforge_watchlist" — user asks about watchlist, stock prices they're tracking
- "finforge_chat" — user asks any other finance question that needs detailed analysis (params: {"message": "original question"})
```

Add dispatch cases in `main.swift` `dispatchNLP()`:

```swift
case "finforge_briefing":
    finforgeAction.briefing { self.reply.send($0) }
case "finforge_portfolio":
    finforgeAction.portfolio { self.reply.send($0) }
case "finforge_predict":
    let symbol = result.params["symbol"] ?? "SPY"
    finforgeAction.predict(symbol: symbol) { self.reply.send($0) }
case "finforge_goals":
    finforgeAction.goals { self.reply.send($0) }
case "finforge_watchlist":
    finforgeAction.watchlist { self.reply.send($0) }
case "finforge_chat":
    let msg = result.params["message"] ?? rawMessage
    finforgeAction.chat(message: msg) { self.reply.send($0) }
```

### Pending Message Poller

Add to `ProactiveMonitor.swift`:

Add a new monitor case `"finforge_poll"` that calls `finforgeAction.pollPending()` on the configured interval (default 60 seconds).

```swift
case "finforge_poll":
    Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { _ in
        self.finforgeAction?.pollPending { }
    }
```

**`pollPending` implementation:**
1. `GET http://localhost:8001/api/v1/natebot/pending` with `X-API-Key` header
2. Parse `{"messages": [...], "count": N}`
3. For each message: `reply.send(message.text)`
4. Log: `log.add(action: "finforge_poll", result: "delivered \(count) message(s)")`
5. The GET itself marks messages as delivered on the FinForge side — no acknowledgment callback needed

Add to `natebot.json` monitors array:

```json
{ "type": "finforge_poll", "interval_seconds": 60 }
```

### Morning Briefing Integration

In `MorningBriefing.swift` `send()` method, after assembling the existing calendar/reminder/goal sections, append the FinForge briefing:

```swift
if let finforge = finforgeAction {
    finforge.briefing { financeBrief in
        fullBriefing += "\n\n" + financeBrief
        self.reply.send(fullBriefing)
        self.log.add(action: "morning_briefing", result: "sent (with finance)")
    }
} else {
    reply.send(fullBriefing)
    log.add(action: "morning_briefing", result: "sent")
}
```

### Initialization in `main.swift`

In the boot sequence, after loading config and creating `ReplyAction`:

```swift
var finforgeAction: FinForgeAction? = nil
if let fc = config.finforge, fc.enabled {
    finforgeAction = FinForgeAction(config: fc, reply: reply, log: activityLog)
    print("[Boot] FinForge integration enabled — polling \(fc.apiUrl)")
}
```

Pass `finforgeAction` to `CommandRouter`, `MorningBriefing`, and `ProactiveMonitor`.

---

## Phase 3: End-to-End Testing

| Test | Steps | Expected |
|------|-------|----------|
| Slash: briefing | Text `/finance` to NateBot | Receive formatted financial summary via iMessage |
| Slash: portfolio | Text `/portfolio` | Receive holdings with vol, beta, TLH flags |
| Slash: predict | Text `/predict AAPL` | Receive drawdown probability with risk level |
| Slash: goals | Text `/fingoals` | Receive goal progress with emoji status |
| Slash: watchlist | Text `/watchlist` | Receive watchlist quotes |
| NLP: finance chat | Text "how's my portfolio doing?" | NLP routes to finforge_portfolio, receive portfolio summary |
| NLP: question | Text "should I be worried about ORCL?" | NLP routes to finforge_chat, receive Claude analysis |
| Poll: goal alert | Wait for goal alert cron (every 4 hours) | Receive goal alert iMessage automatically |
| Poll: TLH signal | Run portfolio analysis with TLH candidate | Receive TLH notification automatically |
| Poll: drawdown | Run drawdown training with >60% position | Receive drawdown warning automatically |
| Briefing: morning | Wait for 7 AM briefing | Morning briefing includes finance section |

---

## Security

- All endpoints require `X-API-Key` header (same key NateBot uses for other services in its `apps` config)
- NateBot runs as the same macOS user — no cross-user access issues
- Docker exposes port 8001 on localhost only (`"8001:8000"` in docker-compose.yml)
- Cloudflare tunnel only exposes the UI (port 3003/80), not the API directly
- No new ports exposed to the internet
- The `/imessage/chat` endpoint reuses the existing chat context builder which excludes merchant names (PII protection)
- Notification queue auto-marks messages as delivered on read — no replay possible

## Emoji Conventions

All iMessage text follows NateBot's existing formatting style:

| Emoji | Meaning |
|-------|---------|
| 💰 | Financial summary / net worth |
| 📊 | Portfolio / market data |
| 🎯 | Goals |
| ✅ | Completed / on track |
| 🟢 | Healthy / low risk |
| ⚠️ | Warning / at risk |
| 🔴 | Error / off track |
| 📉 | Drawdown / loss / TLH |
| 🔮 | ML prediction |
| 👁 | Watchlist |
| 💡 | Claude insight |
| 🔔 | Alerts |

Max message length: 1600 characters. The `cron/notify.py` helper auto-splits longer messages into multiple queue entries.
