"""Watchlists, alert rules and notifications. Signed-in users only; everything is scoped to the
signed-in user and the requested workspace. Ownership is enforced in every query (other users' records
answer 404)."""

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from marketlens_core.alerts import AlertError, notifications, rules, watchlist
from marketlens_core.settings import DataMode

from ...auth import require_user

router = APIRouter(tags=["watchlist & alerts"], dependencies=[Depends(require_user)])

ProductId = Path(..., min_length=1, max_length=128)
RuleId = Path(..., pattern=r"^[0-9a-f]{32}$")
NotificationId = Path(..., pattern=r"^[0-9a-f]{24}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _db(request: Request, mode: DataMode):
    settings = request.app.state.settings
    reason = settings.mode_unavailable_reason(mode)
    if reason:
        raise HTTPException(409, reason)
    return request.app.state.mongo[settings.database_for(mode)]


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AlertError as exc:
        raise HTTPException(exc.status, exc.message)
    except PyMongoError:
        raise HTTPException(503, "The database is unavailable. Try again shortly.")


# ---------- watchlist ----------
class WatchIn(BaseModel):
    notes: str | None = Field(None, max_length=500)
    horizon_date: date | None = None


@router.get("/watchlist")
def get_watchlist(request: Request, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return jsonable_encoder({"mode": mode.value, "items": _call(watchlist.list_items, db, user["_id"])})


@router.put("/watchlist/{product_id}")
def put_watch(request: Request, body: WatchIn, product_id: str = ProductId, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    return jsonable_encoder(_call(watchlist.upsert_item, db, user["_id"], product_id, changes, _now()))


@router.delete("/watchlist/{product_id}", status_code=204)
def delete_watch(request: Request, product_id: str = ProductId, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> Response:
    db = _db(request, mode)
    _call(watchlist.remove_item, db, user["_id"], product_id, _now())
    return Response(status_code=204)


# ---------- alert rules ----------
class RuleIn(BaseModel):
    product_id: str = Field(..., min_length=1, max_length=128)
    type: str = Field("below_target", max_length=40)
    marketplace: str | None = Field(None, max_length=60)
    basis: Literal["base", "delivered"] | None = Field(None, description="Required for below_target; optional for new_low and meaningful_discount")
    target_price_minor: int | None = Field(None, gt=0, description="Integer minor units (paise for INR); below_target only")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    min_score: int | None = Field(None, description="meaningful_discount only: minimum Genuine Discount Score (40-100)")
    cooldown_hours: int = Field(24, ge=0, le=rules.MAX_COOLDOWN_HOURS)
    enabled: bool = True


class RulePatch(BaseModel):
    marketplace: str | None = Field(None, max_length=60)
    basis: Literal["base", "delivered"] | None = None
    target_price_minor: int | None = Field(None, gt=0)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    cooldown_hours: int | None = Field(None, ge=0, le=rules.MAX_COOLDOWN_HOURS)
    min_score: int | None = None
    enabled: bool | None = None
    rearm: bool | None = None


@router.get("/alerts")
def get_rules(request: Request, mode: DataMode = Query(...), include_archived: bool = False, user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return jsonable_encoder({"mode": mode.value, "rules": _call(rules.list_rules, db, user_id=user["_id"], include_archived=include_archived)})


@router.get("/alerts/types")
def get_alert_types(user: dict = Depends(require_user)) -> dict:
    """Every SCOPE alert type with its rule, plus any type that can't be offered yet (none today)."""
    from marketlens_core.alerts.signals import TYPES

    return {"types": [{"type": k, **v} for k, v in TYPES.items()],
            "unavailable": [{"type": k, "reason": v} for k, v in rules.DEFERRED_TYPES.items()]}


@router.post("/alerts", status_code=201)
def post_rule(request: Request, body: RuleIn, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return jsonable_encoder(_call(rules.create_rule, db, user_id=user["_id"], data=body.model_dump(), now=_now(), mode=mode.value))


@router.patch("/alerts/{rule_id}")
def patch_rule(request: Request, body: RulePatch, rule_id: str = RuleId, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    data = {k: getattr(body, k) for k in body.model_fields_set}
    return jsonable_encoder(_call(rules.update_rule, db, user_id=user["_id"], rule_id=rule_id, data=data, now=_now()))


@router.delete("/alerts/{rule_id}", status_code=204)
def delete_rule(request: Request, rule_id: str = RuleId, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> Response:
    db = _db(request, mode)
    _call(rules.archive_rule, db, user_id=user["_id"], rule_id=rule_id, now=_now())
    return Response(status_code=204)


@router.get("/alerts/{rule_id}/events")
def get_rule_events(
    request: Request,
    rule_id: str = RuleId,
    mode: DataMode = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_user),
) -> dict:
    db = _db(request, mode)
    return jsonable_encoder(_call(rules.rule_events, db, user_id=user["_id"], rule_id=rule_id, page=page, page_size=page_size))


# ---------- notifications ----------
@router.get("/notifications")
def get_notifications(
    request: Request,
    mode: DataMode = Query(...),
    status: Literal["active", "unread", "all", "dismissed"] = "active",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_user),
) -> dict:
    db = _db(request, mode)
    return jsonable_encoder({"mode": mode.value, **_call(notifications.list_notifications, db, user_id=user["_id"], status=status, page=page, page_size=page_size)})


@router.get("/notifications/unread-count")
def get_unread(request: Request, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return {"unread": _call(notifications.unread_count, db, user["_id"])}


@router.post("/notifications/read-all")
def post_read_all(request: Request, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return {"marked_read": _call(notifications.read_all, db, user_id=user["_id"], now=_now())}


@router.get("/notifications/{nid}")
def get_notification(request: Request, nid: str = NotificationId, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return jsonable_encoder(_call(notifications.detail, db, user_id=user["_id"], nid=nid))


@router.post("/notifications/{nid}/read")
def post_read(request: Request, nid: str = NotificationId, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return jsonable_encoder(_call(notifications.mark_read, db, user_id=user["_id"], nid=nid, now=_now()))


@router.post("/notifications/{nid}/dismiss")
def post_dismiss(request: Request, nid: str = NotificationId, mode: DataMode = Query(...), user: dict = Depends(require_user)) -> dict:
    db = _db(request, mode)
    return jsonable_encoder(_call(notifications.dismiss, db, user_id=user["_id"], nid=nid, now=_now()))
