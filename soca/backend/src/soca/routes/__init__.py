"""Routes module for SoCa API endpoints."""

from soca.routes.auth import router as auth_router
from soca.routes.criteria import router as criteria_router
from soca.routes.evaluations import router as evaluations_router
from soca.routes.submissions import router as submissions_router

__all__ = [
    "auth_router",
    "submissions_router",
    "criteria_router",
    "evaluations_router",
]
