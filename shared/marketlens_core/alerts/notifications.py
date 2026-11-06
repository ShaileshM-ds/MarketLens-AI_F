"""In-app notifications: owner-only reads, read/dismiss state. Dismissing never deletes evidence."""

from datetime import datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from ..db import ALERT_RULES, EMAIL_OUTBOX, NOTIFICATIONS, OBSERVATIONS
from . import AlertError
from .rules import view as rule_view

TITLE = "New qualifying observation detected"
STATUSES = ("active", "unread", "all", "dismissed")


def message_for(basis: str, marketplace: str | None) -> str:
    what = "base price" if basis == "base" else "confirmed delivered price (base + known shipping)"
    return f"A newly imported observation from {marketplace or 'a store'} has a {what} at or below your target."


def view(n: dict, email: dict | None = None) -> dict:
    return {
        "id": n["_id"],
        "title": n["title"],
        "message": n["message"],
        "rule_id": n["rule_id"],
        "type": n.get("type", "below_target"),
        "evidence": n.get("evidence"),
        "product_id": n["product_id"],
        "product_name": n.get("product_name"),
        "marketplace": n.get("marketplace"),
        "listing_id": n.get("listing_id"),
        "basis": n.get("basis"),
        "observed_minor": n.get("observed_minor"),
        "target_minor": n.get("target_minor"),
        "currency": n.get("currency"),
        "observation_id": n.get("observation_id"),
        "ingestion_run_id": n.get("ingestion_run_id"),
        "source_timestamp": n.get("source_timestamp"),
        "timestamp_quality": n.get("timestamp_quality"),
        "observed_at": n.get("observed_at"),
        "synthetic": n.get("synthetic"),
        "source_label": n.get("source_label"),
        "mode": n.get("mode"),
        "created_at": n["created_at"],
        "read": n.get("read_at") is not None,
        "read_at": n.get("read_at"),
        "dismissed": n.get("dismissed_at") is not None,
        "email": {"status": email["status"], "note": email["note"]} if email else None,
    }


def _filter(user_id: str, status: str) -> dict:
    q = {"user_id": user_id}
    if status == "active":
        q["dismissed_at"] = None
    elif status == "unread":
        q.update({"dismissed_at": None, "read_at": None})
    elif status == "dismissed":
        q["dismissed_at"] = {"$ne": None}
    return q


def unread_count(db: Database, user_id: str) -> int:
    return db[NOTIFICATIONS].count_documents({"user_id": user_id, "read_at": None, "dismissed_at": None})


def list_notifications(db: Database, *, user_id: str, status: str, page: int, page_size: int) -> dict:
    q = _filter(user_id, status)
    total = db[NOTIFICATIONS].count_documents(q)
    docs = list(db[NOTIFICATIONS].find(q).sort([("created_at", -1), ("_id", 1)]).skip((page - 1) * page_size).limit(page_size))
    emails = {e["notification_id"]: e for e in db[EMAIL_OUTBOX].find({"notification_id": {"$in": [d["_id"] for d in docs]}})}
    return {
        "total": total,
        "unread": unread_count(db, user_id),
        "page": page,
        "page_size": page_size,
        "items": [view(d, emails.get(d["_id"])) for d in docs],
    }


def _owned(db: Database, user_id: str, nid: str) -> dict:
    n = db[NOTIFICATIONS].find_one({"_id": nid, "user_id": user_id})
    if not n:
        raise AlertError(404, "That notification doesn't exist.")
    return n


def detail(db: Database, *, user_id: str, nid: str) -> dict:
    n = _owned(db, user_id, nid)
    obs = db[OBSERVATIONS].find_one({"_id": n["observation_id"]}, {"raw": 0, "content_hash": 0}) if n.get("observation_id") else None
    rule = db[ALERT_RULES].find_one({"_id": n["rule_id"], "user_id": user_id})
    email = db[EMAIL_OUTBOX].find_one({"notification_id": nid})
    evidence = None
    if obs:
        evidence = {k: obs.get(k) for k in (
            "listing_id", "marketplace", "currency", "price_minor", "shipping_minor", "shipping_known", "availability",
            "stock_quantity", "source_timestamp", "timestamp_quality", "observed_at", "synthetic", "source_label",
        )}
        evidence["observation_id"] = obs["_id"]
        evidence["ingestion_run_id"] = (obs.get("provenance") or {}).get("ingestion_run_id")
        evidence["ingested_at"] = (obs.get("provenance") or {}).get("ingested_at")
    return {**view(n, email), "observation": evidence, "rule": rule_view(rule) if rule else None}


def mark_read(db: Database, *, user_id: str, nid: str, now: datetime) -> dict:
    _owned(db, user_id, nid)
    n = db[NOTIFICATIONS].find_one_and_update(
        {"_id": nid, "user_id": user_id, "read_at": None}, {"$set": {"read_at": now}}, return_document=ReturnDocument.AFTER
    ) or _owned(db, user_id, nid)
    return view(n, db[EMAIL_OUTBOX].find_one({"notification_id": nid}))


def dismiss(db: Database, *, user_id: str, nid: str, now: datetime) -> dict:
    _owned(db, user_id, nid)
    n = db[NOTIFICATIONS].find_one_and_update(
        {"_id": nid, "user_id": user_id},
        [{"$set": {"dismissed_at": {"$ifNull": ["$dismissed_at", now]}, "read_at": {"$ifNull": ["$read_at", now]}}}],
        return_document=ReturnDocument.AFTER,
    )
    return view(n, db[EMAIL_OUTBOX].find_one({"notification_id": nid}))


def read_all(db: Database, *, user_id: str, now: datetime) -> int:
    return db[NOTIFICATIONS].update_many({"user_id": user_id, "read_at": None, "dismissed_at": None}, {"$set": {"read_at": now}}).modified_count
