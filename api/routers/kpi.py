"""KPI router — exposes aggregated financial metrics for external dashboards."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text

from config import settings
from database import get_db
from services import fire
from services.financial_health import _flow_totals

router = APIRouter(tags=["kpi"])


def verify_kpi_key(x_kpi_api_key: Optional[str] = Header(None)):
    if x_kpi_api_key != settings.kpi_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/kpi")
def get_kpi(db: Session = Depends(get_db), _=Depends(verify_kpi_key)):
    try:
        # Monthly savings rate: (income - expenses) / income for current calendar month.
        # Uses the canonical debits-positive classification shared with
        # financial_health (checking deposits = income; fixed checking debits
        # + credit-card debits = spend; Investment Transfer excluded).
        today = date.today()
        income, essential, discretionary = _flow_totals(db, today.replace(day=1), today)
        expenses = essential + discretionary
        savings_rate = round((income - expenses) / income * 100, 1) if income > 0 else 0.0

        # Net worth: reuse the FIRE engine's definition (cash + invested −
        # credit-card debt). The old raw-SQL sum ADDED credit-card balances,
        # overstating net worth by 2× the debt.
        try:
            current_nw = fire.compute_net_worth(db)["net_worth"]
        except ValueError:
            current_nw = 0.0  # no balance data yet

        # Discretionary spend % over last 30 days (discretionary = non-fixed
        # credit-card spend, total = essential + discretionary)
        _, ess_30, disc_30 = _flow_totals(db, today - timedelta(days=30), today)
        total_spend = ess_30 + disc_30
        disc_pct = round(disc_30 / total_spend * 100, 1) if total_spend > 0 else 0.0

        # Portfolio holdings (latest snapshot date)
        portfolio_res = db.execute(text("""
            SELECT COUNT(*) AS holding_count,
                   SUM(market_value) AS total_value
            FROM holdings
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM holdings)
        """)).fetchone()

        return {
            "project": "finforge",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "kpis": {
                "monthly_savings_rate_pct": {
                    "value": savings_rate,
                    "label": "Monthly Savings Rate",
                    "unit": "%",
                },
                "current_net_worth": {
                    "value": round(current_nw, 2),
                    "label": "Current Net Worth",
                    "unit": "USD",
                },
                "discretionary_spend_pct": {
                    "value": disc_pct,
                    "label": "Discretionary Spend %",
                    "unit": "%",
                },
                "total_holdings": {
                    "value": int(portfolio_res.holding_count or 0) if portfolio_res else 0,
                    "label": "Total Holdings",
                    "unit": "positions",
                },
                "portfolio_value": {
                    "value": round(float(portfolio_res.total_value or 0), 2) if portfolio_res else 0.0,
                    "label": "Portfolio Value",
                    "unit": "USD",
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
