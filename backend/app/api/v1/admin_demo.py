"""Administrator-only Demo data controls. They act only on the Demo database; the worker runs the jobs."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from marketlens_core.demo import generator
from marketlens_core.settings import DataMode

from ...auth import require_admin

router = APIRouter(prefix="/admin/demo", tags=["admin: demo"], dependencies=[Depends(require_admin)])
RESET_PHRASE = "RESET DEMO"


def _demo_db(request: Request):
    s = request.app.state.settings
    return request.app.state.mongo[s.database_for(DataMode.DEMO)]


class ResetIn(BaseModel):
    confirm: str


@router.get("/status")
def demo_status(request: Request) -> dict:
    return jsonable_encoder(generator.status(_demo_db(request)))


@router.post("/generate")
def demo_generate(request: Request, user: dict = Depends(require_admin)) -> dict:
    try:
        return generator.queue_job(_demo_db(request), "demo_generate", user["username"], datetime.now(timezone.utc))
    except generator.DemoError as exc:
        raise HTTPException(409, str(exc))


@router.post("/reset")
def demo_reset(body: ResetIn, request: Request, user: dict = Depends(require_admin)) -> dict:
    if body.confirm != RESET_PHRASE:
        raise HTTPException(422, f"Type {RESET_PHRASE} to confirm. Only the Demo database is affected.")
    return generator.queue_job(_demo_db(request), "demo_reset", user["username"], datetime.now(timezone.utc))
