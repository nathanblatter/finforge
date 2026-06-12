"""Budget endpoints — monthly per-category spending limits with live progress."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Budget, Transaction
from schemas.schemas import (
    BudgetItem,
    BudgetsListResponse,
    BudgetUpsertRequest,
)

router = APIRouter(tags=["budgets"])

WARNING_PCT = 80.0


def _month_spend(db: Session, category: str, year: int, month: int) -> Decimal:
    """Total non-pending debit spend for a category in the given month."""
    rows = (
        db.query(Transaction.amount)
        .filter(
            Transaction.category == category,
            Transaction.is_pending.is_(False),
            extract("year", Transaction.date) == year,
            extract("month", Transaction.date) == month,
        )
        .all()
    )
    # Plaid stores debits (spending) as positive amounts.
    return sum((r[0] for r in rows if r[0] and r[0] > 0), Decimal("0"))


def _status(pct: float) -> str:
    if pct >= 100:
        return "over"
    if pct >= WARNING_PCT:
        return "warning"
    return "ok"


@router.get("/budgets", response_model=BudgetsListResponse)
def list_budgets(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> BudgetsListResponse:
    """All budgets with this month's spend and progress."""
    today = date.today()
    month_str = f"{today.year}-{today.month:02d}"

    budgets = db.query(Budget).order_by(Budget.category).all()
    items: list[BudgetItem] = []
    for b in budgets:
        spent = _month_spend(db, b.category, today.year, today.month)
        limit = Decimal(b.monthly_limit)
        pct = float(spent / limit * 100) if limit > 0 else 0.0
        items.append(BudgetItem(
            category=b.category,
            monthly_limit=limit,
            spent=spent.quantize(Decimal("0.01")),
            pct=round(pct, 1),
            status=_status(pct),
        ))
    return BudgetsListResponse(budgets=items, month=month_str)


@router.put("/budgets", response_model=BudgetItem)
def upsert_budget(
    body: BudgetUpsertRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> BudgetItem:
    """Create or update the monthly limit for a category."""
    category = body.category.strip()
    if not category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is required")
    if body.monthly_limit <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Limit must be positive")

    budget = db.query(Budget).filter_by(category=category).first()
    if budget is None:
        budget = Budget(category=category, monthly_limit=body.monthly_limit)
        db.add(budget)
    else:
        budget.monthly_limit = body.monthly_limit
    db.commit()

    today = date.today()
    spent = _month_spend(db, category, today.year, today.month)
    limit = Decimal(body.monthly_limit)
    pct = float(spent / limit * 100) if limit > 0 else 0.0
    return BudgetItem(
        category=category,
        monthly_limit=limit,
        spent=spent.quantize(Decimal("0.01")),
        pct=round(pct, 1),
        status=_status(pct),
    )


@router.delete("/budgets/{category}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    category: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> None:
    """Remove a category budget."""
    budget = db.query(Budget).filter_by(category=category).first()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    db.delete(budget)
    db.commit()
