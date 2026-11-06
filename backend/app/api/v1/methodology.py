"""Methodology constants (read from the code) and the rolling-origin forecast evaluation report."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pymongo.errors import PyMongoError

from marketlens_core.forecast import evaluation_report
from marketlens_core.history import HistoryError, parse_utc
from marketlens_core.methodology import methodology
from marketlens_core.settings import DataMode

router = APIRouter(tags=["methodology"])


@router.get("/methodology")
def get_methodology() -> dict:
    return methodology()


@router.get("/forecast-evaluation")
def get_forecast_evaluation(
    request: Request,
    mode: DataMode = Query(DataMode.DEMO),
    cutoff: str = Query(..., description="Explicit UTC cutoff; nothing later is read"),
    basis: Literal["base", "delivered"] = Query("base"),
) -> dict:
    settings = request.app.state.settings
    reason = settings.mode_unavailable_reason(mode)
    if reason:
        raise HTTPException(409, reason)
    db = request.app.state.mongo[settings.database_for(mode)]
    try:
        r = evaluation_report(db, cutoff=parse_utc(cutoff, "cutoff"), basis=basis)
    except HistoryError as exc:
        raise HTTPException(422, str(exc))
    except PyMongoError:
        raise HTTPException(503, "The database is unavailable. Try again shortly.")
    return jsonable_encoder({"mode": mode.value, **r})
