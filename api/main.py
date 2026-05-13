"""FinForge API — entry point."""

import logging
import logging.config
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from middleware import register_middleware
from routers import (
    alerts_router,
    auth_router,
    balances_router,
    chat_router,
    goals_router,
    health_router,
    insights_router,
    investments_router,
    kpi_router,
    natebot_router,
    natebot_imessage_router,
    plaid_link_router,
    portfolio_analysis_router,
    reimbursement_router,
    reports_router,
    schwab_auth_router,
    schwab_data_router,
    spending_router,
    summary_router,
    users_router,
    watchlists_router,
)
from routers.system import router as system_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("finforge.api")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "FinForge API starting up — environment=%s version=%s",
        settings.environment,
        app.version,
    )
    yield
    logger.info("FinForge API shutting down.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FinForge API",
    version="1.0.0",
    description="Self-hosted personal finance platform API.",
    lifespan=lifespan,
)

# CORS — open in development; tighten origins list in production
_allow_origins = (
    ["*"]
    if settings.environment == "development"
    else ["http://localhost:3000"]  # extend as needed for prod domains
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_middleware(app)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

_PREFIX = "/api/v1"

app.include_router(auth_router,        prefix=_PREFIX)
app.include_router(health_router,      prefix=_PREFIX)
app.include_router(summary_router,     prefix=_PREFIX)
app.include_router(balances_router,    prefix=_PREFIX)
app.include_router(spending_router,    prefix=_PREFIX)
app.include_router(goals_router,       prefix=_PREFIX)
app.include_router(alerts_router,      prefix=_PREFIX)
app.include_router(investments_router, prefix=_PREFIX)
app.include_router(insights_router,    prefix=_PREFIX)
app.include_router(chat_router,        prefix=_PREFIX)
app.include_router(natebot_router,          prefix=_PREFIX)
app.include_router(natebot_imessage_router, prefix=_PREFIX)
app.include_router(plaid_link_router,       prefix=_PREFIX)
app.include_router(schwab_auth_router, prefix=_PREFIX)
app.include_router(portfolio_analysis_router, prefix=_PREFIX)
app.include_router(reimbursement_router, prefix=_PREFIX)
app.include_router(reports_router,       prefix=_PREFIX)
app.include_router(schwab_data_router, prefix=_PREFIX)
app.include_router(watchlists_router,  prefix=_PREFIX)
app.include_router(users_router,       prefix=_PREFIX)
app.include_router(system_router,      prefix=_PREFIX)
app.include_router(kpi_router,         prefix=_PREFIX)
