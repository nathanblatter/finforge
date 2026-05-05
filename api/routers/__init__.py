from routers.alerts import router as alerts_router
from routers.auth import router as auth_router
from routers.balances import router as balances_router
from routers.chat import router as chat_router
from routers.goals import router as goals_router
from routers.health import router as health_router
from routers.insights import router as insights_router
from routers.investments import router as investments_router
from routers.natebot import router as natebot_router
from routers.natebot_imessage import router as natebot_imessage_router
from routers.spending import router as spending_router
from routers.plaid_link import router as plaid_link_router
from routers.schwab_auth import router as schwab_auth_router
from routers.schwab_data import router as schwab_data_router
from routers.portfolio_analysis import router as portfolio_analysis_router
from routers.summary import router as summary_router
from routers.users import router as users_router
from routers.reimbursement import router as reimbursement_router
from routers.reports import router as reports_router
from routers.watchlists import router as watchlists_router

__all__ = [
    "alerts_router",
    "auth_router",
    "balances_router",
    "chat_router",
    "goals_router",
    "health_router",
    "insights_router",
    "investments_router",
    "natebot_router",
    "plaid_link_router",
    "schwab_auth_router",
    "schwab_data_router",
    "spending_router",
    "natebot_imessage_router",
    "portfolio_analysis_router",
    "summary_router",
    "reimbursement_router",
    "reports_router",
    "users_router",
    "watchlists_router",
]
