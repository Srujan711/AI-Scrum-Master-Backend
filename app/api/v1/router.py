from fastapi import APIRouter
from .backlog import router as backlog_router
from .sprints import router as sprints_router
from .integrations import router as integrations_router
from .standups import router as standups_router

api_router = APIRouter()

# Include all sub-routers
api_router.include_router(backlog_router, prefix="/backlog", tags=["backlog"])
api_router.include_router(sprints_router, prefix="/sprints", tags=["sprints"])
api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])
api_router.include_router(standups_router, prefix="/standups", tags=["standups"])

