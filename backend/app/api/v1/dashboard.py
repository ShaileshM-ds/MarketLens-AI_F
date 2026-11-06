"""Analyst dashboard (read-only, one workspace). Historical figures take an explicit UTC cutoff."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pymongo.errors import PyMongoError

from marketlens_core.dashboard import dashboard, dashboard_meta
from marketlens_core.history import HistoryError, parse_utc
from marketlens_core.settings import DataMode

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _db(request: Request, mode: DataMode):
    settings = request.app.state.settings
    reason = settings.mode_unavailable_reason(mode)
    if reason:
        raise HTTPException(409, reason)
    return request.app.state.mongo[settings.database_for(mode)]


@router.get("/meta")
def meta(request: Request, mode: DataMode = Query(DataMode.DEMO)) -> dict:
    try:
        return jsonable_encoder({"mode": mode.value, **dashboard_meta(_db(request, mode))})
    except PyMongoError:
        raise HTTPException(503, "The database is unavailable. Try again shortly.")


@router.get("")
def get_dashboard(
    request: Request,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff; nothing observed later is read"),
    window: int = Query(90, description="30, 90 or 180 days"),
    category: str | None = Query(None, max_length=60),
    marketplace: str | None = Query(None, max_length=60),
) -> dict:
    db = _db(request, mode)
    try:
        d = dashboard(db, cutoff=parse_utc(cutoff, "cutoff"), window_days=window, category=category, marketplace=marketplace)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        raise HTTPException(503, "The database is unavailable. Try again shortly.")
    return jsonable_encoder({"mode": mode.value, **d})
