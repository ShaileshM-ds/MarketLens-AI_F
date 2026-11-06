from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from marketlens_core import __version__
from marketlens_core.settings import DataMode

router = APIRouter(tags=["health"])


class ModeStatus(BaseModel):
    database: str
    available: bool
    reason: str | None


class Health(BaseModel):
    status: str  # "ok" or "degraded"
    service: str
    version: str
    checked_at: str  # ISO 8601 UTC
    mongo: str  # "ok" or "unavailable"
    modes: dict[DataMode, ModeStatus]


@router.get("/health", response_model=Health)
def health(request: Request, response: Response) -> Health:
    settings = request.app.state.settings
    try:
        request.app.state.mongo.admin.command("ping")
        mongo = "ok"
    except PyMongoError:
        mongo = "unavailable"
        response.status_code = 503

    modes = {}
    for mode in DataMode:
        reason = settings.mode_unavailable_reason(mode)
        modes[mode] = ModeStatus(database=settings.database_for(mode), available=reason is None, reason=reason)

    return Health(
        status="ok" if mongo == "ok" else "degraded",
        service="api",
        version=__version__,
        checked_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        mongo=mongo,
        modes=modes,
    )
