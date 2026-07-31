"""FinForge Cron — scheduled data-sync and maintenance jobs.

All job functions are stubs that will be filled in Phase 2 and Phase 3.
The scheduler runs in blocking mode so the container stays alive.
"""

import json
import logging
import logging.config
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# Attach DB handler so logs are persisted for the UI log viewer
from log_handler import DBLogHandler
_db_handler = DBLogHandler()
_db_handler.setLevel(logging.INFO)
_db_handler.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger().addHandler(_db_handler)

logger = logging.getLogger("finforge.cron")

TIMEZONE = "America/Los_Angeles"
REFRESH_TOKEN_LIFETIME_DAYS = 7
REFRESH_TOKEN_WARN_DAYS = 2  # warn when fewer than this many days remain

# ---------------------------------------------------------------------------
# Job stubs — each logs its invocation and returns immediately.
# Implementations will be added in Phase 2 (Plaid/Schwab sync) and
# Phase 3 (goal engine + Claude insights).
# ---------------------------------------------------------------------------


def plaid_sync() -> None:
    """Pull latest transactions and balances from Plaid."""
    logger.info("Running plaid_sync...")
    try:
        from integrations.plaid_sync import run_plaid_sync
        run_plaid_sync()
        logger.info("plaid_sync completed successfully.")
    except Exception:
        logger.error("plaid_sync failed:\n%s", traceback.format_exc())


def schwab_sync() -> None:
    """Pull latest holdings and balances from Schwab Direct API."""
    logger.info("Running schwab_sync...")
    try:
        from integrations.schwab_sync import run_schwab_sync
        run_schwab_sync()
        logger.info("schwab_sync completed successfully.")
    except Exception:
        logger.error("schwab_sync failed:\n%s", traceback.format_exc())


def generate_goal_snapshots() -> None:
    """Compute and persist today's progress snapshot for every active goal."""
    logger.info("Running generate_goal_snapshots...")
    try:
        from goal_engine import run_generate_goal_snapshots
        run_generate_goal_snapshots()
        logger.info("generate_goal_snapshots completed successfully.")
    except Exception:
        logger.error("generate_goal_snapshots failed:\n%s", traceback.format_exc())


def generate_claude_insights() -> None:
    """Call the Anthropic API to produce daily financial insights."""
    logger.info("Running generate_claude_insights...")
    try:
        from claude_engine import run_generate_claude_insights
        run_generate_claude_insights()
        logger.info("generate_claude_insights completed successfully.")
    except Exception:
        logger.error("generate_claude_insights failed:\n%s", traceback.format_exc())


def check_goal_alerts() -> None:
    """Evaluate alert thresholds and dispatch NateBot notifications if triggered."""
    logger.info("Running check_goal_alerts...")
    try:
        from goal_engine import run_check_goal_alerts
        run_check_goal_alerts()
        logger.info("check_goal_alerts completed successfully.")
    except Exception:
        logger.error("check_goal_alerts failed:\n%s", traceback.format_exc())


def check_budget_alerts() -> None:
    """Evaluate monthly category budgets and notify on 80%/100% crossings."""
    logger.info("Running check_budget_alerts...")
    try:
        from alerts_engine import run_check_budget_alerts
        run_check_budget_alerts()
        logger.info("check_budget_alerts completed successfully.")
    except Exception:
        logger.error("check_budget_alerts failed:\n%s", traceback.format_exc())


def check_price_alerts() -> None:
    """Compare active price alerts to cached quotes and fire one-shot alerts."""
    logger.info("Running check_price_alerts...")
    try:
        from alerts_engine import run_check_price_alerts
        run_check_price_alerts()
        logger.info("check_price_alerts completed successfully.")
    except Exception:
        logger.error("check_price_alerts failed:\n%s", traceback.format_exc())


def check_subscription_hikes() -> None:
    """Detect recurring-charge price increases and notify."""
    logger.info("Running check_subscription_hikes...")
    try:
        from alerts_engine import run_check_subscription_hikes
        run_check_subscription_hikes()
        logger.info("check_subscription_hikes completed successfully.")
    except Exception:
        logger.error("check_subscription_hikes failed:\n%s", traceback.format_exc())


def annual_wrapped() -> None:
    """Generate last year's FinForge Wrapped via the API and text the narrative."""
    logger.info("Running annual_wrapped...")
    try:
        import httpx
        from datetime import date as _date

        api_key = os.environ.get("API_KEY", "")
        year = _date.today().year - 1
        r = httpx.get(
            f"http://finforge-api:8000/api/v1/reports/wrapped?year={year}",
            headers={"X-API-Key": api_key},
            timeout=120,
        )
        r.raise_for_status()
        narrative = r.json().get("narrative")
        if narrative:
            from notify import queue_notification
            queue_notification("wrapped", f"🎁 FinForge Wrapped {year}\n\n{narrative}", priority="normal")
        logger.info("annual_wrapped completed successfully.")
    except Exception:
        logger.error("annual_wrapped failed:\n%s", traceback.format_exc())


def financial_health_snapshot() -> None:
    """Compute this month's financial health score via the API and store it
    as a snapshot (mirrors annual_wrapped's pattern of calling the API rather
    than re-implementing scoring logic in the cron container). The API also
    runs the >10-point month-over-month score-drop alert as part of this call."""
    logger.info("Running financial_health_snapshot...")
    try:
        import httpx

        api_key = os.environ.get("API_KEY", "")
        r = httpx.post(
            "http://finforge-api:8000/api/v1/financial-health/snapshot",
            headers={"X-API-Key": api_key},
            timeout=120,
        )
        r.raise_for_status()
        score = r.json().get("composite_score")
        logger.info("financial_health_snapshot completed successfully — score=%s", score)
    except Exception:
        logger.error("financial_health_snapshot failed:\n%s", traceback.format_exc())


def market_regime() -> None:
    """Classify the current market regime from SPY price action."""
    logger.info("Running market_regime...")
    try:
        from integrations.market_regime import run_market_regime
        run_market_regime()
        logger.info("market_regime completed successfully.")
    except Exception:
        logger.error("market_regime failed:\n%s", traceback.format_exc())


def market_intel() -> None:
    """Flag upcoming earnings and IV spikes on held positions."""
    logger.info("Running market_intel...")
    try:
        from integrations.market_intel import run_market_intel
        run_market_intel()
        logger.info("market_intel completed successfully.")
    except Exception:
        logger.error("market_intel failed:\n%s", traceback.format_exc())


def spending_anomalies() -> None:
    """Flag statistically unusual transactions and possible duplicate charges."""
    logger.info("Running spending_anomalies...")
    try:
        from spending_anomalies import run_spending_anomalies
        run_spending_anomalies()
        logger.info("spending_anomalies completed successfully.")
    except Exception:
        logger.error("spending_anomalies failed:\n%s", traceback.format_exc())


def category_model_train() -> None:
    """Retrain the merchant→category classifier on labeled transactions."""
    logger.info("Running category_model_train...")
    try:
        from integrations.category_model import train_category_model
        train_category_model()
        logger.info("category_model_train completed successfully.")
    except Exception:
        logger.error("category_model_train failed:\n%s", traceback.format_exc())


def weekly_digest() -> None:
    """Assemble and email the weekly financial digest."""
    logger.info("Running weekly_digest...")
    try:
        from digest import run_weekly_digest
        run_weekly_digest()
        logger.info("weekly_digest completed successfully.")
    except Exception:
        logger.error("weekly_digest failed:\n%s", traceback.format_exc())


def deliver_imessages() -> None:
    """Flush the NateBot queue to the imessage-api gateway as real iMessages."""
    try:
        from imessage_delivery import deliver_pending_notifications
        deliver_pending_notifications()
    except Exception:
        logger.error("deliver_imessages failed:\n%s", traceback.format_exc())


def drawdown_model_train() -> None:
    """Train/retrain the drawdown prediction model."""
    logger.info("Running drawdown_model_train...")
    try:
        from integrations.drawdown_model import train_and_persist
        train_and_persist()
        logger.info("drawdown_model_train completed successfully.")
    except Exception:
        logger.error("drawdown_model_train failed:\n%s", traceback.format_exc())


def portfolio_analysis_sync() -> None:
    """Compute portfolio risk, rebalancing drift, and TLH signals."""
    logger.info("Running portfolio_analysis_sync...")
    try:
        from integrations.portfolio_analysis import run_portfolio_analysis
        run_portfolio_analysis()
        logger.info("portfolio_analysis_sync completed successfully.")
    except Exception:
        logger.error("portfolio_analysis_sync failed:\n%s", traceback.format_exc())


def market_data_sync() -> None:
    """Fetch and cache market quotes for all watchlist + portfolio symbols."""
    logger.info("Running market_data_sync...")
    try:
        from integrations.market_data_sync import run_market_data_sync
        run_market_data_sync()
        logger.info("market_data_sync completed successfully.")
    except Exception:
        logger.error("market_data_sync failed:\n%s", traceback.format_exc())


def schwab_token_watchdog() -> None:
    """Check Schwab token freshness and force-refresh to prevent expiry."""
    from datetime import datetime, timedelta, timezone
    from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager
    from config import settings

    try:
        tm = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        tokens = tm.load_tokens()
    except FileNotFoundError:
        logger.warning("[token_watchdog] No Schwab token file — skipping")
        return
    except Exception as exc:
        logger.error("[token_watchdog] Failed to load tokens: %s", exc)
        return

    # Estimate refresh token age: last refresh was at (expires_at - 30min access token lifetime)
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    last_refresh = expires_at - timedelta(minutes=30)
    refresh_token_deadline = last_refresh + timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS)
    days_remaining = (refresh_token_deadline - datetime.now(timezone.utc)).total_seconds() / 86400

    if days_remaining <= 0:
        logger.critical(
            "[token_watchdog] Schwab refresh token has EXPIRED. Manual re-auth required."
        )
        return

    if days_remaining <= REFRESH_TOKEN_WARN_DAYS:
        logger.warning(
            "[token_watchdog] Schwab refresh token expires in %.1f days — forcing refresh now",
            days_remaining,
        )
        try:
            tm.force_refresh()
            logger.info("[token_watchdog] Token refresh successful — 7-day window reset")
        except SchwabReauthRequired:
            logger.critical("[token_watchdog] Refresh token rejected — manual re-auth required")
        except Exception as exc:
            logger.error("[token_watchdog] Token refresh failed: %s", exc)
        return

    logger.info("[token_watchdog] Schwab refresh token OK — %.1f days remaining", days_remaining)


def health_check() -> None:
    """Ping the API health endpoint to confirm services are alive."""
    import httpx
    import os
    api_key = os.environ.get("API_KEY", "")
    try:
        r = httpx.get(
            "http://finforge-api:8000/api/v1/health",
            headers={"X-API-Key": api_key},
            timeout=10,
        )
        if r.is_success:
            logger.debug("Health check OK — status=%s", r.json().get("status"))
        else:
            logger.warning("Health check returned HTTP %d", r.status_code)
    except Exception as exc:
        logger.warning("Health check failed: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=TIMEZONE)

    # Daily jobs — run in the early morning after data is typically available
    scheduler.add_job(
        plaid_sync,
        trigger=CronTrigger(hour=2, minute=0, timezone=TIMEZONE),
        id="plaid_sync",
        name="Plaid Sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        schwab_sync,
        trigger=CronTrigger(hour=2, minute=5, timezone=TIMEZONE),
        id="schwab_sync",
        name="Schwab Sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        market_regime,
        trigger=CronTrigger(hour=2, minute=8, timezone=TIMEZONE),
        id="market_regime",
        name="Market Regime Detection",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        market_intel,
        trigger=CronTrigger(hour=6, minute=30, timezone=TIMEZONE),
        id="market_intel",
        name="Market Intel (Earnings/IV)",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        drawdown_model_train,
        trigger=CronTrigger(hour=2, minute=10, timezone=TIMEZONE),
        id="drawdown_model_train",
        name="Drawdown Model Training",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        portfolio_analysis_sync,
        trigger=CronTrigger(hour=2, minute=15, timezone=TIMEZONE),
        id="portfolio_analysis_sync",
        name="Portfolio Analysis",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        generate_goal_snapshots,
        trigger=CronTrigger(hour=2, minute=30, timezone=TIMEZONE),
        id="generate_goal_snapshots",
        name="Generate Goal Snapshots",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        generate_claude_insights,
        trigger=CronTrigger(hour=3, minute=0, timezone=TIMEZONE),
        id="generate_claude_insights",
        name="Generate Claude Insights",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        check_budget_alerts,
        trigger=CronTrigger(hour=2, minute=45, timezone=TIMEZONE),
        id="check_budget_alerts",
        name="Check Budget Alerts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        check_subscription_hikes,
        trigger=CronTrigger(hour=2, minute=55, timezone=TIMEZONE),
        id="check_subscription_hikes",
        name="Subscription Price-Hike Check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        annual_wrapped,
        trigger=CronTrigger(month=1, day=5, hour=9, minute=0, timezone=TIMEZONE),
        id="annual_wrapped",
        name="Annual FinForge Wrapped",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        financial_health_snapshot,
        trigger=CronTrigger(day=1, hour=4, minute=0, timezone=TIMEZONE),
        id="financial_health_snapshot",
        name="Financial Health Score Snapshot",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        spending_anomalies,
        trigger=CronTrigger(hour=2, minute=50, timezone=TIMEZONE),
        id="spending_anomalies",
        name="Spending Anomaly Detection",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        category_model_train,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=30, timezone=TIMEZONE),
        id="category_model_train",
        name="Category Model Training",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        weekly_digest,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=TIMEZONE),
        id="weekly_digest",
        name="Weekly Email Digest",
        max_instances=1,
        coalesce=True,
    )

    # Interval jobs
    scheduler.add_job(
        check_goal_alerts,
        trigger=IntervalTrigger(hours=4, timezone=TIMEZONE),
        id="check_goal_alerts",
        name="Check Goal Alerts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        market_data_sync,
        trigger=IntervalTrigger(minutes=15, timezone=TIMEZONE),
        id="market_data_sync",
        name="Market Data Sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        check_price_alerts,
        trigger=IntervalTrigger(minutes=15, timezone=TIMEZONE),
        id="check_price_alerts",
        name="Check Price Alerts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        deliver_imessages,
        trigger=IntervalTrigger(minutes=1, timezone=TIMEZONE),
        id="deliver_imessages",
        name="Deliver iMessages",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        health_check,
        trigger=IntervalTrigger(minutes=15, timezone=TIMEZONE),
        id="health_check",
        name="Health Check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        schwab_token_watchdog,
        trigger=IntervalTrigger(hours=6, timezone=TIMEZONE),
        id="schwab_token_watchdog",
        name="Schwab Token Watchdog",
        max_instances=1,
        coalesce=True,
    )

    return scheduler


# ---------------------------------------------------------------------------
# HTTP trigger server — lets the API trigger jobs on demand
# ---------------------------------------------------------------------------

# All runnable jobs (name → function)
ALL_SYNC_JOBS = {
    "plaid_sync": plaid_sync,
    "schwab_sync": schwab_sync,
    "market_data_sync": market_data_sync,
    "drawdown_model_train": drawdown_model_train,
    "portfolio_analysis": portfolio_analysis_sync,
    "generate_goal_snapshots": generate_goal_snapshots,
    "generate_claude_insights": generate_claude_insights,
    "check_goal_alerts": check_goal_alerts,
    "check_budget_alerts": check_budget_alerts,
    "check_price_alerts": check_price_alerts,
    "spending_anomalies": spending_anomalies,
    "category_model_train": category_model_train,
    "market_regime": market_regime,
    "market_intel": market_intel,
    "check_subscription_hikes": check_subscription_hikes,
    "schwab_token_watchdog": schwab_token_watchdog,
    "financial_health_snapshot": financial_health_snapshot,
}


class TriggerHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/run-all":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode())

            # Run all jobs in a background thread so we respond immediately
            def _run_all():
                for name, fn in ALL_SYNC_JOBS.items():
                    logger.info("[trigger] Running %s...", name)
                    fn()

            threading.Thread(target=_run_all, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        logger.debug("trigger-server: %s", format % args)


def start_trigger_server(port: int = 9090) -> None:
    server = HTTPServer(("0.0.0.0", port), TriggerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Trigger server listening on port %d", port)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _startup_token_refresh() -> None:
    """Force-refresh Schwab tokens on startup to reset the 7-day window.
    This prevents token expiry when the cron container has been down."""
    from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager
    from config import settings

    try:
        tm = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        tm.load_tokens()
        tm.force_refresh()
        logger.info("Startup Schwab token refresh successful — 7-day window reset")
    except FileNotFoundError:
        logger.warning("No Schwab token file found — skipping startup refresh")
    except SchwabReauthRequired:
        logger.critical(
            "Schwab refresh token EXPIRED — manual re-auth required via /api/v1/auth/schwab/login"
        )
    except Exception as exc:
        logger.error("Startup Schwab token refresh failed: %s", exc)


if __name__ == "__main__":
    start_trigger_server(9090)

    _startup_token_refresh()

    scheduler = build_scheduler()
    logger.info(
        "FinForge Cron starting — %d jobs registered (timezone=%s)",
        len(scheduler.get_jobs()),
        TIMEZONE,
    )
    for job in scheduler.get_jobs():
        next_run = getattr(job, 'next_run_time', None)
        logger.info("  • %s — next run: %s", job.name, next_run)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("FinForge Cron stopped.")
