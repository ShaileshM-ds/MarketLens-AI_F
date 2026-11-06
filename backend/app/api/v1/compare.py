"""Multi-product comparison (read-only, one workspace)."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pymongo.errors import PyMongoError

from marketlens_core.explorer import MAX_COMPARE, compare_products
from marketlens_core.settings import DataMode

router = APIRouter(tags=["products"])


@router.get("/compare")
def compare(
    request: Request,
    mode: DataMode = Query(DataMode.DEMO),
    ids: list[str] = Query(..., description=f"Product IDs exactly as stored; repeat up to {MAX_COMPARE} times"),
) -> dict:
    settings = request.app.state.settings
    reason = settings.mode_unavailable_reason(mode)
    if reason:
        raise HTTPException(409, reason)
    if any(not i or len(i) > 128 for i in ids):
        raise HTTPException(422, "Each product ID must be 1 to 128 characters.")
    unique = list(dict.fromkeys(ids))
    if len(unique) > MAX_COMPARE:
        raise HTTPException(422, f"Compare at most {MAX_COMPARE} products at a time.")
    db = request.app.state.mongo[settings.database_for(mode)]
    try:
        result = compare_products(db, unique)
    except PyMongoError:
        raise HTTPException(503, "The database is unavailable. Try again shortly.")
    return jsonable_encoder({"mode": mode.value, **result})
