"""SCOPE alert types beyond below_target: new low, meaningful discount, advice change, seller switch,
restock, audit finding, synchronization anomaly. Evaluated in the worker after imports, from verified
observations only, with stable event identities, baselines (no retrospective alerts) and idempotent retries."""

from datetime import timedelta

import pytest

from conftest import p5_import
from helpers import NOW
from marketlens_core.alerts import engine, rules
from test_evidence import row

pytestmark = pytest.mark.integration
T = lambda h: NOW + timedelta(hours=h)  # noqa: E731


def imp(p5, at, rows, policy="require_utc"):
    run = p5_import(p5.db, p5.settings, rows, at, policy=policy, name=f"r-{at.isoformat()}.csv")
    engine.process_alert_jobs(p5.db, now_fn=lambda: at)
    return run


def hist(lid, market, price, days=range(1, 60), ref=1300, **kw):
    return [row(lid, market, price(n) if callable(price) else price, ref, n, urgency_message="", **kw) for n in days]


def rule(p5, at, type_, user="alice", **kw):
    return rules.create_rule(p5.db, user_id=user, data={"product_id": "MCL0001", "type": type_, "cooldown_hours": 0, **kw}, now=at)


def notes(p5, rule_id):
    return list(p5.db.notifications.find({"rule_id": rule_id}).sort("created_at", 1))


def test_meaningful_discount_notifies_once_per_crossing_and_survives_retries(p5):
    imp(p5, T(1), hist("L-A", "Amazon", 1000))
    r = rule(p5, T(2), "meaningful_discount", min_score=70)
    run = imp(p5, T(3), [row("L-A", "Amazon", 700, 1300, 0, urgency_message="")])
    ns = notes(p5, r["id"])
    assert len(ns) == 1
    n = ns[0]
    assert n["type"] == "meaningful_discount" and n["evidence"]["score"] >= 70 and n["evidence"]["savings_percent"] > 25
    assert n["evidence"]["analysis_version"].startswith("evidence-") and n["evidence"]["cutoff"].startswith("2026-10-31")
    assert n["ingestion_run_id"] == run["_id"]
    assert p5.db.email_outbox.find_one({"notification_id": n["_id"]})["status"] == "not_sent"
    # Worker retry of the same job, and a later run with an unchanged finding: no new notification.
    p5.db.jobs.update_many({"type": "alerts"}, {"$set": {"status": "queued"}})
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(4))
    imp(p5, T(5), [row("L-A", "Amazon", 700, 1300, 0, hour=18, urgency_message="")])
    assert len(notes(p5, r["id"])) == 1


def test_advice_change_needs_a_valid_baseline_then_notifies_on_change(p5):
    imp(p5, T(1), hist("L-A", "Amazon", 1000))
    r = rule(p5, T(2), "advice_change")
    imp(p5, T(3), [row("L-A", "Amazon", 1000, 1300, 0, urgency_message="")])
    assert notes(p5, r["id"]) == []  # first evaluation records the baseline only
    stored = p5.db.alert_rules.find_one({"_id": r["id"]})["signal_state"]
    assert stored["code"] == "consider_waiting" and stored["version"].startswith("advice-")
    imp(p5, T(4), [row("L-A", "Amazon", 700, 1300, 0, hour=20, urgency_message="")])
    ns = notes(p5, r["id"])
    assert len(ns) == 1 and ns[0]["evidence"]["previous"] == "consider_waiting" and ns[0]["evidence"]["current"] == "buy_now"
    assert "advice changed" in ns[0]["title"].lower()


def test_snapshot_only_import_never_evaluates_signal_rules(p5):
    r = rule(p5, T(2), "advice_change")
    from conftest import p5_row
    imp(p5, T(3), [p5_row("L-A", "Amazon", "900", "60", timestamp="2026-11-06T10:00:00")], policy="allow_timezone_unknown")
    assert notes(p5, r["id"]) == [] and p5.db.alert_rules.find_one({"_id": r["id"]}).get("signal_state") is None


def test_new_audit_finding_and_unchanged_findings(p5):
    imp(p5, T(1), hist("L-A", "Amazon", 1000))
    r = rule(p5, T(2), "audit_finding")
    imp(p5, T(3), [row("L-A", "Amazon", 1000, 1300, 0, urgency_message="")])
    assert notes(p5, r["id"]) == []  # baseline: already-known findings (unsupported discount) never alert
    imp(p5, T(4), [row("L-A", "Amazon", 1000, 1950, 0, hour=20, urgency_message="")])
    ns = notes(p5, r["id"])
    assert len(ns) == 1 and [f["rule_id"] for f in ns[0]["evidence"]["new_findings"]] == ["reference_inflation"]
    assert "not a legal finding" in ns[0]["message"].lower()
    imp(p5, T(5), [row("L-A", "Amazon", 1000, 1950, 0, hour=22, urgency_message="")])
    assert len(notes(p5, r["id"])) == 1


def test_synchronization_anomaly(p5):
    step = lambda n: 1100 if 25 <= n < 40 else 1000  # noqa: E731  two matched changes so far: not a pattern
    imp(p5, T(1), hist("L-A", "Amazon", step) + hist("L-F", "Flipkart", step))
    r = rule(p5, T(2), "synchronization_anomaly")
    imp(p5, T(3), [row("L-A", "Amazon", 1000, 1300, 0, urgency_message=""), row("L-F", "Flipkart", 1000, 1300, 0, urgency_message="")])
    assert notes(p5, r["id"]) == []
    # Next day (1 Nov): both listings move again together. A same-day change wouldn't alter the daily lowest price.
    imp(p5, T(4), [row("L-A", "Amazon", 1100, 1300, -1, urgency_message=""), row("L-F", "Flipkart", 1100, 1300, -1, urgency_message="")])
    ns = notes(p5, r["id"])
    assert len(ns) == 1 and "not proof" in ns[0]["message"].lower()
    assert ns[0]["evidence"]["new_patterns"][0]["matched"] >= 3


def test_seller_switch(p5):
    imp(p5, T(1), hist("L-A", "Amazon", 1000) + hist("L-F", "Flipkart", 1050))
    r = rule(p5, T(2), "seller_switch")
    imp(p5, T(3), [row("L-A", "Amazon", 1000, 1300, 0, urgency_message=""), row("L-F", "Flipkart", 1050, 1300, 0, urgency_message="")])
    assert notes(p5, r["id"]) == []
    imp(p5, T(4), [row("L-A", "Amazon", 1100, 1300, 0, hour=20, urgency_message="")])
    ns = notes(p5, r["id"])
    assert len(ns) == 1 and ns[0]["evidence"]["previous"]["seller_id"] == "S-L-A" and ns[0]["evidence"]["current"]["seller_id"] == "S-L-F"


def test_new_low_and_restock_use_new_verified_observations(p5):
    imp(p5, T(1), hist("L-A", "Amazon", 1000) + [row("L-F", "Flipkart", 1200, 1300, n, urgency_message="", availability="Out of Stock", stock_quantity="0") for n in (2, 1)])
    low = rule(p5, T(2), "new_low", basis="base")
    back = rule(p5, T(2), "restock", marketplace="Flipkart")
    imp(p5, T(3), [row("L-A", "Amazon", 950, 1300, 0, urgency_message=""), row("L-F", "Flipkart", 1200, 1300, 0, urgency_message="")])
    ln, rn = notes(p5, low["id"]), notes(p5, back["id"])
    assert len(ln) == 1 and ln[0]["observed_minor"] == 95000 and ln[0]["evidence"]["previous_low_minor"] == 100000
    assert len(rn) == 1 and rn[0]["listing_id"] == "L-F" and rn[0]["evidence"]["previous_availability"] == "Out of Stock"
    imp(p5, T(4), [row("L-A", "Amazon", 960, 1300, 0, hour=18, urgency_message="")])
    assert len(notes(p5, low["id"])) == 1  # 960 is not below the 950 low
    imp(p5, T(5), [row("L-A", "Amazon", 940, 1300, 0, hour=20, urgency_message="")])
    assert len(notes(p5, low["id"])) == 2


def test_insufficient_history_and_no_retrospective(p5):
    imp(p5, T(1), hist("L-A", "Amazon", 1000, days=range(1, 8)))
    r = rule(p5, T(2), "meaningful_discount", min_score=40)
    imp(p5, T(3), [row("L-A", "Amazon", 500, 1300, 0, urgency_message="")])
    assert notes(p5, r["id"]) == []
    assert p5.db.alert_events.find_one({"rule_id": r["id"]})["outcome"] == "insufficient"
    late = rule(p5, T(9), "new_low", basis="base")
    p5.db.jobs.update_many({"type": "alerts"}, {"$set": {"status": "queued"}})
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(10))  # earlier runs replayed after the rule exists
    assert notes(p5, late["id"]) == []


def test_api_types_validation_ownership_and_notifications(p5):
    imp(p5, T(1), hist("L-A", "Amazon", 1000))
    Q = {"mode": "imported"}
    types = p5.alice.get("/api/v1/alerts/types", params=Q).json()
    assert {t["type"] for t in types["types"]} == {"below_target", "new_low", "meaningful_discount", "advice_change", "seller_switch", "restock", "audit_finding", "synchronization_anomaly"}
    assert types["unavailable"] == []
    bad = p5.alice.post("/api/v1/alerts", params=Q, json={"product_id": "MCL0001", "type": "meaningful_discount", "min_score": 20})
    assert bad.status_code == 422
    ok = p5.alice.post("/api/v1/alerts", params=Q, json={"product_id": "MCL0001", "type": "meaningful_discount", "min_score": 60, "cooldown_hours": 0})
    assert ok.status_code == 201, ok.text
    rid = ok.json()["id"]
    assert ok.json()["type"] == "meaningful_discount" and ok.json()["min_score"] == 60
    assert p5.bob.get(f"/api/v1/alerts/{rid}/events", params=Q).status_code == 404
    imp(p5, NOW + timedelta(days=30), [row("L-A", "Amazon", 700, 1300, 0, urgency_message="")])
    items = p5.alice.get("/api/v1/notifications", params=Q).json()["items"]
    n = next(i for i in items if i["rule_id"] == rid)
    assert n["type"] == "meaningful_discount" and n["read"] is False and n["evidence"]["score"] >= 60
    d = p5.alice.get(f"/api/v1/notifications/{n['id']}", params=Q).json()
    assert d["evidence"]["cutoff"].startswith("2026-10-31") and d["rule"]["type"] == "meaningful_discount"
    assert p5.alice.post(f"/api/v1/notifications/{n['id']}/read", params=Q).json()["read"] is True
    assert p5.bob.get(f"/api/v1/notifications/{n['id']}", params=Q).status_code == 404
    ev = p5.alice.get(f"/api/v1/alerts/{rid}/events", params=Q).json()["items"]
    assert ev[0]["outcome"] == "notified" and ev[0]["type"] == "meaningful_discount"
