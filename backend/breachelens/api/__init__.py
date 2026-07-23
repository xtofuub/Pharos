"""BreachLens API routers."""
from .auth import router as auth_router
from .health import router as health_router
from .sources import router as sources_router
from .indexing import router as indexing_router
from .search import router as search_router
from .results import router as results_router
from .aggregations import router as aggregations_router
from .audit import router as audit_router
from .settings import router as settings_router
from .stats import router as stats_router

__all__ = [
    "auth_router", "health_router", "sources_router", "indexing_router",
    "search_router", "results_router", "aggregations_router", "audit_router",
    "settings_router", "stats_router",
]
