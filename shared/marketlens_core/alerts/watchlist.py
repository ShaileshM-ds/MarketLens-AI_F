"""Personal watchlists: one entry per user, workspace (database) and product."""

import uuid
from datetime import date, datetime

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..db import ALERT_RULES, PRODUCTS, WATCHLIST_ITEMS
from ..explorer import compare_products
from . import AlertError


def _view(item: dict, product: dict | None = None, alerts: dict | None = None) -> dict:
    return {
        "product_id": item["product_id"],
        "notes": item.get("notes"),
        "horizon_date": item.get("horizon_date"),
        "added_at": item.get("added_at"),
        "updated_at": item.get("updated_at"),
        "product": product,
        "alerts": alerts or {"active": 0, "paused": 0},
    }


def ensure_product(db: Database, product_id: str) -> dict:
    p = db[PRODUCTS].find_one({"_id": product_id}, {"name": 1})
    if not p:
        raise AlertError(404, f"No product '{product_id}' in this workspace.")
    return p


def upsert_item(db: Database, user_id: str, product_id: str, changes: dict, now: datetime) -> dict:
    """Add a product, or merge new settings into the existing entry (only the fields given change)."""
    ensure_product(db, product_id)
    fields = {}
    if "notes" in changes:
        notes = changes["notes"]
        fields["notes"] = notes.strip() if isinstance(notes, str) and notes.strip() else None
    if "horizon_date" in changes:
        h = changes["horizon_date"]
        fields["horizon_date"] = h.isoformat() if isinstance(h, date) else h
    update = {
        "$set": {**fields, "updated_at": now},
        "$setOnInsert": {"_id": uuid.uuid4().hex, "user_id": user_id, "product_id": product_id, "added_at": now},
    }
    for attempt in range(2):  # a concurrent first insert can race the unique index once
        try:
            item = db[WATCHLIST_ITEMS].find_one_and_update(
                {"user_id": user_id, "product_id": product_id}, update, upsert=True, return_document=ReturnDocument.AFTER
            )
            return _view(item)
        except DuplicateKeyError:
            if attempt:
                raise
    raise AssertionError("unreachable")


def remove_item(db: Database, user_id: str, product_id: str, now: datetime) -> None:
    """Idempotent. The product's alert rules are archived (kept for history), not deleted."""
    db[WATCHLIST_ITEMS].delete_one({"user_id": user_id, "product_id": product_id})
    db[ALERT_RULES].update_many(
        {"user_id": user_id, "product_id": product_id, "status": "active"},
        {"$set": {"status": "archived", "enabled": False, "archived_at": now, "updated_at": now}},
    )


def list_items(db: Database, user_id: str) -> list[dict]:
    items = list(db[WATCHLIST_ITEMS].find({"user_id": user_id}).sort("added_at", -1).limit(500))
    pids = [i["product_id"] for i in items]
    products = {p["product_id"]: p for p in compare_products(db, pids)["products"]} if pids else {}
    counts: dict[str, dict] = {}
    for r in db[ALERT_RULES].find({"user_id": user_id, "status": "active", "product_id": {"$in": pids}}, {"product_id": 1, "enabled": 1}):
        c = counts.setdefault(r["product_id"], {"active": 0, "paused": 0})
        c["active" if r.get("enabled") else "paused"] += 1
    return [_view(i, products.get(i["product_id"]), counts.get(i["product_id"])) for i in items]


def horizons(db: Database, pairs: set[tuple[str, str]]) -> dict[tuple[str, str], str | None]:
    """(user_id, product_id) -> watch-until date, for evaluation."""
    if not pairs:
        return {}
    users = sorted({u for u, _ in pairs})
    pids = sorted({p for _, p in pairs})
    out = {}
    for i in db[WATCHLIST_ITEMS].find({"user_id": {"$in": users}, "product_id": {"$in": pids}}, {"user_id": 1, "product_id": 1, "horizon_date": 1}):
        out[(i["user_id"], i["product_id"])] = i.get("horizon_date")
    return out
