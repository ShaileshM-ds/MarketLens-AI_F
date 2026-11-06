"""Target-price alert rules: validation, lifecycle and snapshot context.

`below_target` compares each new observation with a target price. The other SCOPE types (signals.py) are
evaluated from verified history after imports; they take no target price.
"""

import uuid
from datetime import datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from ..db import ALERT_EVENTS, ALERT_RULES, PRODUCTS
from ..explorer import product_detail
from ..money import MoneyError, minor_digits
from ..pricing import delivered_price
from . import AlertError
from .signals import BASIS_TYPES, DEFAULT_MIN_SCORE, MARKETPLACE_TYPES, MIN_SCORE_RANGE, TYPES
from .watchlist import ensure_product, upsert_item

BASES = ("base", "delivered")
MAX_COOLDOWN_HOURS = 720
MAX_RULES_PER_PRODUCT = 10
DEFERRED_TYPES: dict[str, str] = {}  # every SCOPE alert type is implemented
SIGNAL_NOTE = ("Evaluated only when new verified (UTC) observations are imported for this product. The first evaluation "
               "records a baseline; existing data never triggers a notification.")
CONTEXT_NOTE = (
    "Context only: these are existing imported snapshot observations. They never trigger a notification; "
    "only observations imported after this alert is active are evaluated."
)


def view(rule: dict, product_name: str | None = None) -> dict:
    return {
        "id": rule["_id"],
        "product_id": rule["product_id"],
        "product_name": product_name,
        "type": rule.get("type", "below_target"),
        "marketplace": rule.get("marketplace"),
        "basis": rule.get("basis"),
        "target_price_minor": rule.get("target_price_minor"),
        "currency": rule.get("currency"),
        "min_score": rule.get("min_score"),
        "cooldown_hours": rule["cooldown_hours"],
        "enabled": rule["enabled"],
        "armed": rule["armed"],
        "status": rule["status"],
        "created_at": rule["created_at"],
        "updated_at": rule.get("updated_at"),
        "active_since": rule["active_since"],
        "last_evaluated": rule.get("last_evaluated"),
        "last_triggered_at": rule.get("last_triggered_at"),
        "last_notification_id": rule.get("last_notification_id"),
    }


def _product_facts(db: Database, product_id: str) -> dict:
    d = product_detail(db, product_id)
    if d is None:
        raise AlertError(404, f"No product '{product_id}' in this workspace.")
    return d


def _validate(d: dict, fields: dict) -> None:
    t = fields.get("type", "below_target")
    if t in DEFERRED_TYPES:
        raise AlertError(422, f"Alert type '{t}' is not available yet: {DEFERRED_TYPES[t]}.")
    if t not in TYPES:
        raise AlertError(422, f"Unknown alert type '{t}'.")
    if t != "below_target":
        return _validate_signal(d, fields)
    if fields.get("basis") not in BASES:
        raise AlertError(422, "Price basis must be 'base' (listing price) or 'delivered' (base + known shipping).")
    target = fields.get("target_price_minor")
    if isinstance(target, bool) or not isinstance(target, int):
        raise AlertError(422, "Target price must be an integer number of minor units.")
    if target <= 0:
        raise AlertError(422, "Target price must be greater than 0.")
    cur = fields.get("currency") or ""
    try:
        minor_digits(cur)
    except MoneyError:
        raise AlertError(422, f"Currency '{cur}' is not supported.") from None
    product_currency = d["pricing"]["currency"]
    if product_currency is None:
        raise AlertError(422, "This product has no single currency to compare against, so a price alert can't be set safely.")
    if cur != product_currency:
        raise AlertError(422, f"This product is priced in {product_currency}; the alert currency must match.")
    m = fields.get("marketplace")
    if m is not None and m not in d["product"]["marketplaces"]:
        raise AlertError(422, f"{d['product']['product_id']} is not sold on {m} in this workspace.")
    cd = fields.get("cooldown_hours", 24)
    if isinstance(cd, bool) or not isinstance(cd, int) or not 0 <= cd <= MAX_COOLDOWN_HOURS:
        raise AlertError(422, f"Cooldown must be a whole number of hours from 0 to {MAX_COOLDOWN_HOURS}.")


def _validate_signal(d: dict, fields: dict) -> None:
    t = fields["type"]
    if fields.get("marketplace") is not None:
        if t not in MARKETPLACE_TYPES:
            raise AlertError(422, f"A store filter isn't available for '{t}' alerts.")
        if fields["marketplace"] not in d["product"]["marketplaces"]:
            raise AlertError(422, f"{d['product']['product_id']} is not sold on {fields['marketplace']} in this workspace.")
    if t in BASIS_TYPES and fields.get("basis") not in BASES:
        raise AlertError(422, "Price basis must be 'base' (listing price) or 'delivered' (base + known shipping).")
    if t == "meaningful_discount":
        ms = fields.get("min_score")
        lo, hi = MIN_SCORE_RANGE
        if isinstance(ms, bool) or not isinstance(ms, int) or not lo <= ms <= hi:
            raise AlertError(422, f"Minimum Genuine Discount Score must be a whole number from {lo} to {hi}.")
    cd = fields.get("cooldown_hours", 24)
    if isinstance(cd, bool) or not isinstance(cd, int) or not 0 <= cd <= MAX_COOLDOWN_HOURS:
        raise AlertError(422, f"Cooldown must be a whole number of hours from 0 to {MAX_COOLDOWN_HOURS}.")


def current_context(d: dict, rule: dict) -> dict:
    """Which current snapshot listings would satisfy the rule now (shown, never notified)."""
    if rule.get("type", "below_target") != "below_target":
        return {"qualifying_now": [], "note": SIGNAL_NOTE}
    rows = []
    for o in d["offers"]:
        if rule.get("marketplace") and o["marketplace"] != rule["marketplace"]:
            continue
        value = o["price_minor"] if rule["basis"] == "base" else delivered_price(o["price_minor"], o["shipping_minor"], o["shipping_known"])
        if value is None or not o["purchasable"] or o["currency"] != rule["currency"]:
            continue
        if value <= rule["target_price_minor"]:
            rows.append({"marketplace": o["marketplace"], "listing_id": o["listing_id"], "value_minor": value})
    rows.sort(key=lambda r: (r["value_minor"], r["listing_id"]))
    return {"qualifying_now": rows, "note": CONTEXT_NOTE}


def create_rule(db: Database, *, user_id: str, data: dict, now: datetime, mode: str = "imported") -> dict:
    fields = {"type": "below_target", "cooldown_hours": 24, "enabled": True, "marketplace": None, **data}
    if fields["type"] == "meaningful_discount" and fields.get("min_score") is None:
        fields["min_score"] = DEFAULT_MIN_SCORE
    if fields["type"] in BASIS_TYPES and fields["type"] != "below_target":
        fields["basis"] = fields.get("basis") or "base"
    d = _product_facts(db, fields.get("product_id", ""))
    _validate(d, fields)
    if db[ALERT_RULES].count_documents({"user_id": user_id, "product_id": d["product"]["product_id"], "status": "active"}) >= MAX_RULES_PER_PRODUCT:
        raise AlertError(422, f"You can have at most {MAX_RULES_PER_PRODUCT} alerts for one product.")
    upsert_item(db, user_id, d["product"]["product_id"], {}, now)
    rule = {
        "_id": uuid.uuid4().hex,
        "user_id": user_id,
        "mode": mode,
        "product_id": d["product"]["product_id"],
        "type": fields["type"],
        "marketplace": fields["marketplace"],
        "basis": fields.get("basis"),
        "target_price_minor": fields.get("target_price_minor") if fields["type"] == "below_target" else None,
        "currency": fields.get("currency") if fields["type"] == "below_target" else None,
        "min_score": fields.get("min_score") if fields["type"] == "meaningful_discount" else None,
        "cooldown_hours": fields["cooldown_hours"],
        "enabled": bool(fields["enabled"]),
        "armed": True,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "active_since": now,
        "last_evaluated": None,
        "last_triggered_at": None,
        "last_notification_id": None,
    }
    db[ALERT_RULES].insert_one(rule)
    return {**view(rule, d["product"]["name"]), "current_context": current_context(d, rule)}


def _owned(db: Database, user_id: str, rule_id: str) -> dict:
    rule = db[ALERT_RULES].find_one({"_id": rule_id, "user_id": user_id})
    if not rule:
        raise AlertError(404, "That alert doesn't exist.")
    return rule


def update_rule(db: Database, *, user_id: str, rule_id: str, data: dict, now: datetime) -> dict:
    rule = _owned(db, user_id, rule_id)
    if rule["status"] != "active":
        raise AlertError(409, "This alert was deleted and can't be changed.")
    editable = {k: data[k] for k in ("marketplace", "basis", "target_price_minor", "currency", "cooldown_hours", "min_score") if k in data}
    merged = {**rule, **editable}
    d = _product_facts(db, rule["product_id"])
    _validate(d, merged)
    sets = {**editable, "updated_at": now}
    if "enabled" in data:
        enable = bool(data["enabled"])
        sets["enabled"] = enable
        if enable and not rule["enabled"]:
            # Resuming never replays observations imported while paused.
            sets["active_since"] = now
            sets["armed"] = True
    if data.get("rearm"):
        sets["armed"] = True
    updated = db[ALERT_RULES].find_one_and_update({"_id": rule_id, "user_id": user_id}, {"$set": sets}, return_document=ReturnDocument.AFTER)
    return {**view(updated, d["product"]["name"]), "current_context": current_context(d, updated)}


def archive_rule(db: Database, *, user_id: str, rule_id: str, now: datetime) -> None:
    _owned(db, user_id, rule_id)
    db[ALERT_RULES].update_one({"_id": rule_id, "user_id": user_id}, {"$set": {"status": "archived", "enabled": False, "archived_at": now, "updated_at": now}})


def list_rules(db: Database, *, user_id: str, include_archived: bool = False) -> list[dict]:
    q = {"user_id": user_id} if include_archived else {"user_id": user_id, "status": "active"}
    rules = list(db[ALERT_RULES].find(q).sort("created_at", -1).limit(500))
    names = {p["_id"]: p.get("name") for p in db[PRODUCTS].find({"_id": {"$in": list({r["product_id"] for r in rules})}}, {"name": 1})}
    return [view(r, names.get(r["product_id"])) for r in rules]


def rule_events(db: Database, *, user_id: str, rule_id: str, page: int, page_size: int) -> dict:
    _owned(db, user_id, rule_id)
    q = {"rule_id": rule_id, "user_id": user_id}
    total = db[ALERT_EVENTS].count_documents(q)
    items = [
        {k: e.get(k) for k in ("observation_id", "listing_id", "marketplace", "value_minor", "target_minor", "basis", "currency", "outcome", "reason",
                               "notification_id", "ingestion_run_id", "evaluated_at", "type", "cutoff", "state")}
        for e in db[ALERT_EVENTS].find(q).sort("evaluated_at", -1).skip((page - 1) * page_size).limit(page_size)
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


__all__ = ["create_rule", "update_rule", "archive_rule", "list_rules", "rule_events", "ensure_product"]
