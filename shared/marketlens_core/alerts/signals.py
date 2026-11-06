"""SCOPE alert types beyond `below_target`, evaluated in the worker after an import run (version SIGNALS_VERSION).

When a rule is evaluated
- Only when the run inserted verified (UTC) observations for the rule's product, ingested after the rule's
  `active_since`. Snapshot-only imports never evaluate these rules, and earlier runs are never replayed.
- The analysis cutoff is the product's latest verified observation time (never an ingestion time).

Two families
- Event types (new_low, restock) look at each new verified observation and compare it only with earlier
  verified observations. Event identity: (rule, observation).
- State types (meaningful_discount, advice_change, audit_finding, synchronization_anomaly, seller_switch)
  compare the analysis at this cutoff with the state stored on the rule. The first evaluation records a
  baseline and never notifies (no retrospective alerts). An unchanged result is never a new event.
  Event identity: (rule, analysis version, previous -> current state, cutoff).
- meaningful_discount is crossing-based: it disarms after notifying and re-arms when it no longer qualifies.

Idempotency follows engine.py: one evaluation record per (rule, run); notification _id = event key; a retry
finds the evaluation record (skip) or the notification (recover) and never duplicates.
"""

from datetime import timedelta

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..advice import ADVICE_VERSION, buying_advice
from ..audit import AUDIT_VERSION, product_audit
from ..db import ALERT_EVENTS, ALERT_RULES, NOTIFICATIONS, OBSERVATIONS, OFFERS, PRODUCTS
from ..evidence import EVIDENCE_VERSION, _unusable, price_evidence
from ..explorer import availability_class
from ..history import _aware, _iso, _value
from ..sync import SYNC_VERSION, product_sync
from .delivery import deliver
from .watchlist import horizons

SIGNALS_VERSION = "signals-1"
WINDOW = 90
NEW_LOW_LOOKBACK_DAYS = 90
NEW_LOW_MIN_DAYS = 14
SWITCH_FRESH_DAYS = 7
DEFAULT_MIN_SCORE = 70
MIN_SCORE_RANGE = (40, 100)
TYPES = {
    "below_target": {"label": "Below target price", "description": "A newly imported observation at or below your target price.", "family": "observation"},
    "new_low": {"label": "New lowest verified price",
                "description": f"A new verified observation lower than every verified price of this product in the previous {NEW_LOW_LOOKBACK_DAYS} days "
                               f"(needs {NEW_LOW_MIN_DAYS}+ earlier observed days).", "family": "event"},
    "restock": {"label": "Back in stock (reported)", "description": "A listing reported out of stock in its previous verified observation is reported in stock again.", "family": "event"},
    "meaningful_discount": {"label": "Meaningful discount",
                            "description": "The Real Price Detector finds a genuine reduction and the Genuine Discount Score reaches your minimum (needs 14+ observed days).", "family": "state"},
    "advice_change": {"label": "Buying advice change", "description": "Buying advice changes between two valid evaluations under the same rules version.", "family": "state"},
    "seller_switch": {"label": "Lowest-price seller change", "description": "A different seller ID has the lowest current verified price among in-stock listings.", "family": "state"},
    "audit_finding": {"label": "New pricing audit finding", "description": "A pricing-audit rule triggers that wasn't triggered at the previous evaluation. Flags for review, not accusations.", "family": "state"},
    "synchronization_anomaly": {"label": "New synchronized price pattern",
                                "description": "A pair of store listings newly shows synchronized price changes. A pattern worth investigating, not proof.", "family": "state"},
}
SIGNAL_TYPES = [t for t, v in TYPES.items() if v["family"] != "observation"]
MARKETPLACE_TYPES = {"below_target", "new_low", "restock"}
BASIS_TYPES = {"below_target", "new_low", "meaningful_discount"}


def _key(rule_id: str, material: str) -> str:
    from .engine import event_key

    return event_key(rule_id, material)


def _ev(title, message, material, evidence, obs=None, value=None):
    return {"title": title, "message": message, "material": material, "evidence": evidence, "obs": obs, "value": value}


# ---------------- handlers: return (outcome, reason, events, new_state or None) ----------------

def _meaningful(db, rule, run_obs, cutoff):
    e = price_evidence(db, rule["product_id"], cutoff=cutoff, window_days=WINDOW, basis=rule.get("basis") or "base")
    if e["status"] != "available":
        return "insufficient", e["reason"], [], None
    d, ev = e["detector"], e["evidence"]
    q = d["verdict"] == "below_usual" and e["score"]["value"] >= rule.get("min_score", DEFAULT_MIN_SCORE)
    state = {"qualifies": q, "score": e["score"]["value"], "version": EVIDENCE_VERSION, "cutoff": e["cutoff"]}
    if not q:
        return "not_qualifying", None, [], {**state, "armed": True}
    if not (rule.get("signal_state") or {}).get("armed", True):
        return "no_change", "Already notified for this discount; re-arms when it no longer qualifies.", [], {**state, "armed": False}
    evidence = {"analysis_version": EVIDENCE_VERSION, "cutoff": e["cutoff"], "score": e["score"]["value"], "band": e["score"]["band"],
                "savings_percent": d["savings_percent"], "current_minor": d["current_minor"], "usual_minor": d["baseline_minor"], "currency": d["currency"],
                "marketplace": ev["marketplace"], "listing_id": ev["listing_id"], "observed_at": ev["current_observation"]["observed_at"],
                "advertised_discount_percent": d["advertised_discount_percent"], "min_score": rule.get("min_score", DEFAULT_MIN_SCORE)}
    msg = (f"Verified history shows the current price {d['savings_percent']}% below its usual level, with a Genuine Discount Score of "
           f"{e['score']['value']} / 100 (your minimum: {evidence['min_score']}).")
    return "notified", None, [_ev("Meaningful discount found in verified history", msg, f"meaningful|{EVIDENCE_VERSION}|{e['cutoff']}", evidence,
                                  value=d["current_minor"])], {**state, "armed": False}


def _state_change(rule, current: dict, version: str, compare_key: str):
    prev = rule.get("signal_state")
    if not prev or prev.get("version") != version:
        return "baseline", prev
    return ("no_change" if prev.get(compare_key) == current.get(compare_key) else "changed"), prev


def _advice(db, rule, run_obs, cutoff):
    a = buying_advice(db, rule["product_id"], cutoff=cutoff, window_days=WINDOW, basis="base")
    code = a["recommendation"]["code"]
    if code == "insufficient_evidence":
        return "insufficient", a["recommendation"]["reason"], [], None  # never a comparison point
    state = {"code": code, "version": ADVICE_VERSION, "cutoff": a["cutoff"], "confidence": a["confidence"]["level"]}
    kind, prev = _state_change(rule, state, ADVICE_VERSION, "code")
    if kind != "changed":
        return ("baseline_recorded" if kind == "baseline" else "no_change"), None, [], state
    labels = {"buy_now": "Buy now", "consider_waiting": "Consider waiting"}
    evidence = {"analysis_version": ADVICE_VERSION, "cutoff": a["cutoff"], "previous": prev["code"], "previous_cutoff": prev.get("cutoff"),
                "current": code, "confidence": a["confidence"]["level"], "reason": a["recommendation"]["reason"]}
    msg = f"Buying advice changed from {labels[prev['code']]} to {labels[code]} ({a['confidence']['level']} confidence): {a['recommendation']['reason']}"
    return "notified", None, [_ev("Buying advice changed", msg, f"advice|{ADVICE_VERSION}|{prev['code']}>{code}|{a['cutoff']}", evidence)], state


def _set_change(rule, keys: list, version: str):
    prev = rule.get("signal_state")
    if not prev or prev.get("version") != version:
        return "baseline", []
    return "changed", sorted(set(keys) - set(prev.get("keys") or []))


def _audit(db, rule, run_obs, cutoff):
    au = product_audit(db, rule["product_id"], cutoff=cutoff, window_days=WINDOW)
    by_key = {f"{f['rule_id']}@{f['rule_version']}": f for f in au["findings"]}
    state = {"keys": sorted(by_key), "version": AUDIT_VERSION, "cutoff": au["cutoff"]}
    kind, new = _set_change(rule, list(by_key), AUDIT_VERSION)
    if kind == "baseline":
        return "baseline_recorded", None, [], state
    if not new:
        return "no_change", None, [], state
    found = [{k: by_key[n][k] for k in ("rule_id", "rule_version", "title", "kind", "severity", "explanation")} for n in new]
    msg = (f"New pricing audit finding{'s' if len(found) > 1 else ''}: {', '.join(f['title'] for f in found)}. "
           "These are flags for review, not a legal finding or an accusation.")
    return "notified", None, [_ev("New pricing audit finding", msg, f"audit|{','.join(new)}|{au['cutoff']}",
                                  {"analysis_version": AUDIT_VERSION, "cutoff": au["cutoff"], "new_findings": found})], state


def _sync(db, rule, run_obs, cutoff):
    sy = product_sync(db, rule["product_id"], cutoff=cutoff, window_days=WINDOW)
    pats = {f"{p['a']['listing_id']}|{p['b']['listing_id']}@{SYNC_VERSION}": p for p in sy["pairs"] if p["status"] == "pattern"}
    state = {"keys": sorted(pats), "version": SYNC_VERSION, "cutoff": sy["cutoff"]}
    kind, new = _set_change(rule, list(pats), SYNC_VERSION)
    if kind == "baseline":
        return "baseline_recorded", None, [], state
    if not new:
        return "no_change", None, [], state
    found = [{"a": {k: pats[n]["a"][k] for k in ("listing_id", "seller_id", "marketplace")}, "b": {k: pats[n]["b"][k] for k in ("listing_id", "seller_id", "marketplace")},
              "matched": pats[n]["matched"], "summary": pats[n]["summary"]} for n in new]
    msg = "Store listings of this product newly show synchronized price changes. This is a pattern worth investigating, not proof of coordination."
    return "notified", None, [_ev("New synchronized price pattern", msg, f"sync|{','.join(new)}|{sy['cutoff']}",
                                  {"analysis_version": SYNC_VERSION, "cutoff": sy["cutoff"], "new_patterns": found})], state


def _cheapest(db, product_id, cutoff):
    cands = []
    for off in db[OFFERS].find({"product_id": product_id}).sort("_id", 1):
        o = db[OBSERVATIONS].find_one({"listing_id": off["_id"], "history_eligible": True, "observed_at": {"$lte": cutoff}},
                                      {"raw": 0, "content_hash": 0}, sort=[("observed_at", -1), ("_id", -1)])
        if o and not _unusable(o, "base") and (cutoff - _aware(o["observed_at"])).days <= SWITCH_FRESH_DAYS:
            cands.append((o["price_minor"], off["_id"], off.get("seller_id"), off.get("marketplace"), o.get("currency"), o))
    if not cands or len({c[4] for c in cands}) > 1:
        return None
    p, lid, sid, m, cur, o = min(cands, key=lambda c: (c[0], c[1]))
    return {"listing_id": lid, "seller_id": sid, "marketplace": m, "price_minor": p, "currency": cur, "observed_at": _iso(o["observed_at"]), "observation_id": o["_id"]}


def _switch(db, rule, run_obs, cutoff):
    c = _cheapest(db, rule["product_id"], cutoff)
    if c is None:
        return "insufficient", "No current, in-stock verified listing in a single currency.", [], None
    state = {**c, "version": "switch-1", "cutoff": _iso(cutoff)}
    kind, prev = _state_change(rule, state, "switch-1", "seller_id")
    if kind != "changed":
        return ("baseline_recorded" if kind == "baseline" else "no_change"), None, [], state
    pv = {k: prev.get(k) for k in ("listing_id", "seller_id", "marketplace", "price_minor", "observed_at")}
    msg = f"The lowest current verified price moved from seller {pv['seller_id']} ({pv['marketplace']}) to seller {c['seller_id']} ({c['marketplace']})."
    return "notified", None, [_ev("Lowest-price seller changed", msg, f"switch|{pv['seller_id']}>{c['seller_id']}|{_iso(cutoff)}",
                                  {"analysis_version": "switch-1", "cutoff": _iso(cutoff), "previous": pv, "current": c}, value=c["price_minor"])], state


def _new_low(db, rule, run_obs, cutoff):
    basis = rule.get("basis") or "base"
    events, insufficient = [], 0
    for o in run_obs:
        if rule.get("marketplace") and o.get("marketplace") != rule["marketplace"]:
            continue
        if _unusable(o, basis):
            continue
        v = _value(o, basis)
        at = _aware(o["observed_at"])
        q = {"product_id": rule["product_id"], "history_eligible": True, "currency": o.get("currency"), "_id": {"$ne": o["_id"]},
             "observed_at": {"$gte": at - timedelta(days=NEW_LOW_LOOKBACK_DAYS), "$lt": at}}
        if rule.get("marketplace"):
            q["marketplace"] = rule["marketplace"]
        prior = [(_aware(p["observed_at"]).date(), _value(p, basis)) for p in db[OBSERVATIONS].find(q, {"raw": 0, "content_hash": 0}) if not _unusable(p, basis)]
        if len({d for d, _ in prior}) < NEW_LOW_MIN_DAYS:
            insufficient += 1
            continue
        low = min(x for _, x in prior)
        if v < low:
            ev = {"analysis_version": SIGNALS_VERSION, "cutoff": _iso(at), "previous_low_minor": low, "lookback_days": NEW_LOW_LOOKBACK_DAYS,
                  "prior_observed_days": len({d for d, _ in prior}), "basis": basis, "currency": o.get("currency")}
            events.append(_ev("New lowest verified price", f"A new verified observation on {o.get('marketplace')} is lower than every verified price "
                              f"of this product in the previous {NEW_LOW_LOOKBACK_DAYS} days.", f"new_low|{o['_id']}", ev, obs=o, value=v))
    if events:
        return "notified", None, events, None
    return ("insufficient" if insufficient else "not_qualifying"), (f"Fewer than {NEW_LOW_MIN_DAYS} earlier observed days." if insufficient else None), [], None


def _restock(db, rule, run_obs, cutoff):
    events = []
    for o in run_obs:
        if rule.get("marketplace") and o.get("marketplace") != rule["marketplace"]:
            continue
        if availability_class(o.get("availability")) not in ("in_stock", "limited_stock") or "stock_availability_contradiction" in (o.get("flags") or []):
            continue
        prev = db[OBSERVATIONS].find_one({"listing_id": o["listing_id"], "history_eligible": True, "observed_at": {"$lt": o["observed_at"]}},
                                         {"raw": 0, "content_hash": 0}, sort=[("observed_at", -1), ("_id", -1)])
        if prev and availability_class(prev.get("availability")) == "out_of_stock":
            ev = {"analysis_version": SIGNALS_VERSION, "cutoff": _iso(o["observed_at"]), "previous_availability": prev.get("availability"),
                  "previous_observed_at": _iso(prev["observed_at"]), "previous_observation_id": prev["_id"], "availability": o.get("availability")}
            events.append(_ev("Back in stock (reported)", f"{o.get('marketplace')} reports this listing as {o.get('availability')} after an out-of-stock observation.",
                              f"restock|{o['_id']}", ev, obs=o, value=o.get("price_minor")))
    return ("notified", None, events, None) if events else ("not_qualifying", None, [], None)


HANDLERS = {"meaningful_discount": _meaningful, "advice_change": _advice, "audit_finding": _audit, "synchronization_anomaly": _sync,
            "seller_switch": _switch, "new_low": _new_low, "restock": _restock}


# ---------------- evaluation ----------------

def evaluate_signals_for_run(db: Database, run_id: str, now) -> dict:
    summary = {"signal_evaluated": 0, "signal_notified": 0}
    pids = db[OBSERVATIONS].distinct("product_id", {"provenance.ingestion_run_id": run_id, "history_eligible": True})
    if not pids:
        return summary
    rules = list(db[ALERT_RULES].find({"product_id": {"$in": pids}, "status": "active", "enabled": True, "type": {"$in": SIGNAL_TYPES}}).sort("_id", 1))
    if not rules:
        return summary
    hz = horizons(db, {(r["user_id"], r["product_id"]) for r in rules})
    names = {p["_id"]: p.get("name") for p in db[PRODUCTS].find({"_id": {"$in": pids}}, {"name": 1})}
    for r in rules:
        n = evaluate_signal(db, r, run_id, now, hz.get((r["user_id"], r["product_id"])), names.get(r["product_id"]))
        if n is not None:
            summary["signal_evaluated"] += 1
            summary["signal_notified"] += n
    return summary


def evaluate_signal(db: Database, rule: dict, run_id: str, now, horizon: str | None, product_name: str | None) -> int | None:
    eval_id = _key(rule["_id"], f"run:{run_id}")
    if db[ALERT_EVENTS].find_one({"_id": eval_id}, {"_id": 1}):
        return None  # already evaluated (retry)
    run_obs = list(db[OBSERVATIONS].find({"provenance.ingestion_run_id": run_id, "product_id": rule["product_id"], "history_eligible": True},
                                         {"raw": 0, "content_hash": 0}).sort([("observed_at", 1), ("_id", 1)]))
    if not run_obs:
        return None
    ingested = _aware(run_obs[0]["provenance"]["ingested_at"])
    if ingested <= _aware(rule["active_since"]):
        return None  # stored before the rule was active: never replayed
    latest = db[OBSERVATIONS].find_one({"product_id": rule["product_id"], "history_eligible": True}, {"observed_at": 1}, sort=[("observed_at", -1)])
    cutoff = _aware(latest["observed_at"])
    if horizon and ingested.date().isoformat() > horizon:
        outcome, reason, events, state = "excluded", "watch_period_ended", [], None
    else:
        outcome, reason, events, state = HANDLERS[rule["type"]](db, rule, run_obs, cutoff)

    sent = []
    last = _aware(rule.get("last_triggered_at"))
    for ev in events:
        key = _key(rule["_id"], ev["material"])
        if db[NOTIFICATIONS].find_one({"_id": key}, {"_id": 1}):
            sent.append(key)  # recovered after a crash
            continue
        if last and rule.get("cooldown_hours") and now - last < timedelta(hours=rule["cooldown_hours"]):
            outcome = "suppressed_cooldown"
            continue
        o = ev["obs"] or {}
        note = {
            "_id": key, "user_id": rule["user_id"], "rule_id": rule["_id"], "type": rule["type"], "mode": rule.get("mode", "imported"),
            "product_id": rule["product_id"], "product_name": product_name, "marketplace": o.get("marketplace") or ev["evidence"].get("marketplace"),
            "listing_id": o.get("listing_id") or ev["evidence"].get("listing_id"), "observation_id": o.get("_id"),
            "basis": rule.get("basis"), "observed_minor": ev["value"], "target_minor": None,
            "currency": o.get("currency") or ev["evidence"].get("currency"), "source_timestamp": o.get("source_timestamp"),
            "timestamp_quality": o.get("timestamp_quality"), "observed_at": o.get("observed_at"), "ingestion_run_id": run_id,
            "synthetic": all(x.get("synthetic") for x in run_obs), "source_label": run_obs[0].get("source_label"),
            "title": ev["title"], "message": ev["message"], "evidence": ev["evidence"],
            "created_at": now, "read_at": None, "dismissed_at": None,
        }
        try:
            db[NOTIFICATIONS].insert_one(note)
        except DuplicateKeyError:
            pass
        deliver(db, note, now)
        sent.append(key)
        last = now
    if events and not sent and outcome == "notified":
        outcome = "suppressed_cooldown"
    sets = {"last_evaluated": {"run_id": run_id, "outcome": outcome, "reason": reason, "at": now, "cutoff": _iso(cutoff)}}
    if state is not None:
        sets["signal_state"] = state
    if sent:
        sets.update({"last_triggered_at": now, "last_notification_id": sent[-1]})
    db[ALERT_RULES].update_one({"_id": rule["_id"], "status": "active"}, {"$set": sets})
    try:
        db[ALERT_EVENTS].insert_one({"_id": eval_id, "rule_id": rule["_id"], "user_id": rule["user_id"], "type": rule["type"],
                                     "product_id": rule["product_id"], "ingestion_run_id": run_id, "cutoff": _iso(cutoff),
                                     "outcome": "notified" if sent else outcome, "reason": reason, "notification_id": sent[-1] if sent else None,
                                     "notification_ids": sent, "state": state, "evaluated_at": now})
    except DuplicateKeyError:
        pass
    return len(sent)
