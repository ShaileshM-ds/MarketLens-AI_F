"""Alert evaluation: runs in the worker after an import has durably stored its observations.

Which observations are evaluated
- Only observations inserted by an ingestion run (found by `provenance.ingestion_run_id`). Duplicates are
  never inserted and quarantined rows never become observations, so neither is ever evaluated.
- For a rule, only observations whose ingestion time is later than the rule's `active_since` (creation or
  last resume). Existing snapshots, and observations imported while a rule was paused, are never replayed.

Per (rule, observation)
- Store filter, currency, availability (in stock / limited, no stock contradiction), watch period, and the
  price basis (base, or base + known shipping) decide eligibility; the comparison is exact integer minor units:
  value <= target.
- Re-arm: after notifying, a rule is disarmed until a later evaluated observation is above target (or the
  user re-arms it). Cooldown: no second notification within `cooldown_hours` of the last one.

Idempotency (at most one notification per rule and observation; not "exactly once")
- Event key = sha256(rule_id|observation_id)[:24], used as the _id of both the notification and the event.
  1. An existing event means "already processed": skip.
  2. An existing notification means a crash happened after notifying: record the outcome as notified.
  3. Insert the notification (a duplicate _id is ignored), deliver, update the rule, then insert the event.
- Standalone MongoDB has no multi-document transactions; this order makes every retry safe.
"""

import hashlib
from datetime import date, datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..db import ALERT_EVENTS, ALERT_RULES, JOBS, NOTIFICATIONS, OBSERVATIONS, PRODUCTS
from ..explorer import availability_class
from ..pricing import delivered_price
from .delivery import deliver
from .notifications import TITLE, message_for
from .watchlist import horizons

ALERT_JOB = "alerts"
BATCH = 500
_MIN = datetime.min.replace(tzinfo=timezone.utc)


def event_key(rule_id: str, observation_id: str) -> str:
    return hashlib.sha256(f"{rule_id}|{observation_id}".encode("utf-8")).hexdigest()[:24]


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def classify(rule: dict, obs: dict, horizon: str | None) -> tuple[str, str | None, int | None]:
    """Returns (outcome, reason, value) where outcome is 'qualifies', 'not_qualifying' or 'excluded'."""
    ingested = _aware((obs.get("provenance") or {}).get("ingested_at"))
    if horizon and ingested and ingested.date() > date.fromisoformat(horizon):
        return "excluded", "watch_period_ended", None
    if obs.get("currency") != rule["currency"]:
        return "excluded", "currency_mismatch", None
    if "stock_availability_contradiction" in (obs.get("flags") or []):
        return "excluded", "stock_availability_contradiction", None
    cls = availability_class(obs.get("availability"))
    if cls == "out_of_stock":
        return "excluded", "out_of_stock", None
    if cls not in ("in_stock", "limited_stock"):
        return "excluded", "availability_not_reported", None
    price = obs.get("price_minor")
    if price is None:
        return "excluded", "no_price", None
    if rule["basis"] == "base":
        value = price
    else:
        value = delivered_price(price, obs.get("shipping_minor"), bool(obs.get("shipping_known")))
        if value is None:
            return "excluded", "shipping_unknown", None
    return ("qualifies" if value <= rule["target_price_minor"] else "not_qualifying"), None, value


def _notification(rule: dict, obs: dict, value: int, key: str, product_name: str | None, now: datetime) -> dict:
    return {
        "_id": key,
        "user_id": rule["user_id"],
        "rule_id": rule["_id"],
        "mode": rule.get("mode", "imported"),
        "product_id": obs["product_id"],
        "product_name": product_name,
        "marketplace": obs.get("marketplace"),
        "listing_id": obs.get("listing_id"),
        "observation_id": obs["_id"],
        "basis": rule["basis"],
        "observed_minor": value,
        "target_minor": rule["target_price_minor"],
        "currency": rule["currency"],
        "source_timestamp": obs.get("source_timestamp"),
        "timestamp_quality": obs.get("timestamp_quality"),
        "observed_at": obs.get("observed_at"),
        "ingestion_run_id": (obs.get("provenance") or {}).get("ingestion_run_id"),
        "synthetic": obs.get("synthetic"),
        "source_label": obs.get("source_label"),
        "title": TITLE,
        "message": message_for(rule["basis"], obs.get("marketplace")),
        "created_at": now,
        "read_at": None,
        "dismissed_at": None,
    }


def evaluate_one(db: Database, rule: dict, obs: dict, horizon: str | None, product_name: str | None, now: datetime) -> str | None:
    """Evaluate one observation for one rule. Mutates `rule` in memory to keep a run's sequence consistent."""
    if rule.get("marketplace") and obs.get("marketplace") != rule["marketplace"]:
        return None
    ingested = _aware((obs.get("provenance") or {}).get("ingested_at"))
    if ingested is None or ingested <= _aware(rule["active_since"]):
        return None  # stored before this rule was active: context only, never a notification
    key = event_key(rule["_id"], obs["_id"])
    if db[ALERT_EVENTS].find_one({"_id": key}, {"_id": 1}):
        return None  # already processed
    recovered = db[NOTIFICATIONS].find_one({"_id": key}, {"_id": 1}) is not None
    outcome, reason, value = classify(rule, obs, horizon)
    if recovered:
        outcome, reason = "notified", None
    elif outcome == "qualifies":
        last = _aware(rule.get("last_triggered_at"))
        if not rule.get("armed", True):
            outcome = "suppressed_not_armed"
        elif last and rule.get("cooldown_hours") and now - last < timedelta(hours=rule["cooldown_hours"]):
            outcome = "suppressed_cooldown"
        else:
            outcome = "notified"
            note = _notification(rule, obs, value, key, product_name, now)
            try:
                db[NOTIFICATIONS].insert_one(note)
            except DuplicateKeyError:
                pass
            deliver(db, note, now)

    sets = {"last_evaluated": {"observation_id": obs["_id"], "outcome": outcome, "reason": reason, "at": now}}
    if outcome == "notified":
        sets.update({"armed": False, "last_triggered_at": now, "last_notification_id": key})
    elif outcome == "not_qualifying" and not rule.get("armed", True):
        sets["armed"] = True  # re-arm: a later observation was above target
    db[ALERT_RULES].update_one({"_id": rule["_id"], "status": "active"}, {"$set": sets})
    rule.update(sets)
    try:
        db[ALERT_EVENTS].insert_one(
            {
                "_id": key,
                "rule_id": rule["_id"],
                "user_id": rule["user_id"],
                "observation_id": obs["_id"],
                "listing_id": obs.get("listing_id"),
                "product_id": obs.get("product_id"),
                "marketplace": obs.get("marketplace"),
                "value_minor": value,
                "target_minor": rule["target_price_minor"],
                "basis": rule["basis"],
                "currency": rule["currency"],
                "outcome": outcome,
                "reason": reason,
                "notification_id": key if outcome == "notified" else None,
                "ingestion_run_id": (obs.get("provenance") or {}).get("ingestion_run_id"),
                "evaluated_at": now,
            }
        )
    except DuplicateKeyError:
        pass
    return outcome


def _order(obs: dict):
    # Verified time first when known; otherwise a stable, documented processing order (not market chronology).
    return (_aware(obs.get("observed_at")) or _MIN, obs.get("source_timestamp") or "", obs["_id"])


def evaluate_run(db: Database, run_id: str, now: datetime) -> dict:
    summary = {"observations": 0, "evaluated": 0, "notified": 0}
    projection = {"raw": 0, "content_hash": 0}
    cursor = db[OBSERVATIONS].find({"provenance.ingestion_run_id": run_id}, projection).sort("_id", 1).batch_size(BATCH)
    batch: list[dict] = []

    def flush():
        if not batch:
            return
        pids = sorted({o["product_id"] for o in batch})
        rules_by_product: dict[str, list[dict]] = {}
        for r in db[ALERT_RULES].find({"product_id": {"$in": pids}, "status": "active", "enabled": True, "type": {"$in": ["below_target", None]}}).sort("_id", 1):
            rules_by_product.setdefault(r["product_id"], []).append(r)
        if rules_by_product:
            hz = horizons(db, {(r["user_id"], r["product_id"]) for rs in rules_by_product.values() for r in rs})
            names = {p["_id"]: p.get("name") for p in db[PRODUCTS].find({"_id": {"$in": list(rules_by_product)}}, {"name": 1})}
            for obs in sorted(batch, key=_order):
                for rule in rules_by_product.get(obs["product_id"], []):
                    out = evaluate_one(db, rule, obs, hz.get((rule["user_id"], rule["product_id"])), names.get(obs["product_id"]), now)
                    if out:
                        summary["evaluated"] += 1
                        summary["notified"] += out == "notified"
        summary["observations"] += len(batch)
        batch.clear()

    for obs in cursor:
        batch.append(obs)
        if len(batch) >= BATCH:
            flush()
    flush()
    from .signals import evaluate_signals_for_run  # SCOPE types beyond below_target (verified observations only)

    summary.update(evaluate_signals_for_run(db, run_id, now))
    return summary


def enqueue_alert_job(db: Database, run_id: str, now: datetime) -> None:
    db[JOBS].update_one(
        {"_id": f"alerts|{run_id}"},
        {"$setOnInsert": {"type": ALERT_JOB, "run_id": run_id, "status": "queued", "created_at": now, "attempts": 0}},
        upsert=True,
    )


def process_next_alert_job(db: Database, now_fn) -> dict | None:
    job = db[JOBS].find_one_and_update(
        {"type": ALERT_JOB, "status": "queued"},
        {"$set": {"status": "running", "started_at": now_fn()}, "$inc": {"attempts": 1}},
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if not job:
        return None
    try:
        summary = evaluate_run(db, job["run_id"], now_fn())
        db[JOBS].update_one({"_id": job["_id"]}, {"$set": {"status": "completed", "finished_at": now_fn(), "summary": summary}})
    except Exception as exc:  # stays retryable: evaluation is idempotent
        db[JOBS].update_one({"_id": job["_id"]}, {"$set": {"status": "failed", "finished_at": now_fn(), "error": type(exc).__name__}})
        raise
    return job


def process_alert_jobs(db: Database, now_fn, limit: int = 100) -> int:
    n = 0
    while n < limit and process_next_alert_job(db, now_fn):
        n += 1
    return n


def requeue_stale_alert_jobs(db: Database, now: datetime, older_than: timedelta = timedelta(minutes=10)) -> int:
    """Alert jobs left 'running' by a crashed worker are safe to run again."""
    return db[JOBS].update_many(
        {"type": ALERT_JOB, "status": {"$in": ["running", "failed"]}, "started_at": {"$lt": now - older_than}, "attempts": {"$lt": 5}},
        {"$set": {"status": "queued"}},
    ).modified_count
