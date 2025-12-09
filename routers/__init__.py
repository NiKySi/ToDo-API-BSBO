# routers/__init__.py
from .tasks import router as tasks_router
from .stats import router as stats_router

__all__ = ["tasks_router", "stats_router"]