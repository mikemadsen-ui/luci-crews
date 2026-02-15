"""FastAPI route modules for LUCI CrewAI Service."""

from .analysis import router as analysis_router
from .coaching import router as coaching_router
from .config import router as config_router
from .health import router as health_router

__all__ = [
    "analysis_router",
    "coaching_router",
    "config_router",
    "health_router",
]
