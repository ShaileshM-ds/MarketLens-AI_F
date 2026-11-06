"""Alert evaluation through the real import pipeline (throwaway databases only)."""

from datetime import timedelta

import pytest

from conftest import p5_import, p5_row
from helpers import NOW
from marketlens_core.alerts import engine, rules
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration

T = lambda h: NOW + timedelta(hours=h)  # noqa: E731


def make_rule(p5, at, user="alice", **kw):
    data = {"product_id": "MCL0001", "target_price_minor": 135000, "currency": "INR", "basis": "base", "cooldown_hours": 0, **kw}
    return rules.create_rule(p5.db, user_id=user, data=data, now=at)


def new_obs(p5, at, *rows, policy="require_utc"):
    run = p5_import(p5.db, p5.settings, list(rows), at, policy=policy, name=f"obs-{at.isoformat()}.csv")
    engine.process_alert_jobs(p5.db, now_fn=lambda: at)
    return run


def utc_row(lid, market, price, ship, hour, **kw):
    return p5_row(lid, market, price, ship, timestamp=f"2026-11-05T{hour:02d}:00:00Z", **kw)


def notes(p5, **q):
    return list(p5.db.notifications.find(q))


def events(p5, rule_id):
    return {e["observation_id"]: e for e in p5.db.alert_events.find({"rule_id": rule_id})}


def test_existing_snapshot_never_triggers_a_retrospective_notification(p5):
    make_rule(p5, T(1), target_price_minor=999999)  # every stored snapshot would qualify
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(1))  # the seed import's alert job runs after the rule exists
    assert notes(p5) == []
    assert p5.db.alert_events.count_documents({}) == 0


def test_new_qualifying_observation_notifies_once_and_never_again(p5):
    rule = make_rule(p5, T(1))
    run = new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300", "60", 9))
    ns = notes(p5)
    assert len(ns) == 1
    n = ns[0]
    assert (n["user_id"], n["rule_id"], n["product_id"], n["marketplace"], n["listing_id"]) == ("alice", rule["id"], "MCL0001", "Flipkart", "L-F")
    assert (n["basis"], n["observed_minor"], n["target_minor"], n["currency"]) == ("base", 130000, 135000, "INR")
    assert n["title"] == "New qualifying observation detected"
    assert "drop" not in (n["title"] + n["message"]).lower()
    assert n["ingestion_run_id"] == run["_id"] and n["observation_id"].startswith("obs1|L-F|utc:")
    assert n["synthetic"] is True and n["read_at"] is None and n["mode"] == "imported"
    out = p5.db.email_outbox.find_one({"notification_id": n["_id"]})
    assert out["status"] == "not_sent" and "nothing was sent" in out["note"].lower()

    # Reprocessing the same job (worker restart/retry) changes nothing.
    p5.db.jobs.update_many({"type": "alerts"}, {"$set": {"status": "queued"}})
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(3))
    # Re-importing the same file: duplicates are not stored, so nothing new is evaluated.
    p5_import(p5.db, p5.settings, [utc_row("L-F", "Flipkart", "1300", "60", 9)], T(4), policy="require_utc")
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(4))
    assert len(notes(p5)) == 1
    assert p5.db.email_outbox.count_documents({}) == 1
    stored = p5.db.alert_rules.find_one({"_id": rule["id"]})
    assert stored["last_triggered_at"] is not None and stored["last_evaluated"]["outcome"] == "notified"


def test_delivered_basis_never_counts_unknown_shipping(p5):
    delivered = make_rule(p5, T(1), basis="delivered", target_price_minor=140000)
    base = make_rule(p5, T(1), basis="base", target_price_minor=140000)
    new_obs(p5, T(2), utc_row("L-A", "Amazon", "1200", "", 9))
    ev = list(events(p5, delivered["id"]).values())[0]
    assert ev["outcome"] == "excluded" and ev["reason"] == "shipping_unknown"
    assert [n["rule_id"] for n in notes(p5)] == [base["id"]]


def test_exact_minor_unit_threshold(p5):
    rule = make_rule(p5, T(1), basis="delivered", target_price_minor=136001)
    new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300.01", "60", 9))  # 130001 + 6000 = 136001 <= 136001
    new_obs(p5, T(3), utc_row("L-F", "Flipkart", "1300.02", "60", 10))  # 136002 > target
    outcomes = sorted(e["outcome"] for e in events(p5, rule["id"]).values())
    assert outcomes == ["not_qualifying", "notified"]


def test_store_specific_rules_ignore_other_stores(p5):
    rule = make_rule(p5, T(1), marketplace="Amazon", target_price_minor=200000)
    new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300", "60", 9))
    assert notes(p5) == [] and events(p5, rule["id"]) == {}
    new_obs(p5, T(3), utc_row("L-A", "Amazon", "1300", "60", 10))
    assert [n["marketplace"] for n in notes(p5)] == ["Amazon"]


def test_unavailable_contradictory_and_other_currency_observations_are_excluded(p5):
    rule = make_rule(p5, T(1), target_price_minor=200000)
    new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300", "60", 9, availability="Out of Stock", stock_quantity="0"))
    # A snapshot-rule import keeps a contradiction as a flagged observation (history files would quarantine it).
    new_obs(p5, T(3), p5_row("L-M", "Myntra", "1300", "0", timestamp="2026-11-05T09:00:00", availability="Out of Stock", stock_quantity="25"), policy="allow_timezone_unknown")
    new_obs(p5, T(4), utc_row("L-A", "Amazon", "10", "1", 11, currency="USD"))
    reasons = sorted(e["reason"] for e in events(p5, rule["id"]).values())
    assert reasons == ["currency_mismatch", "out_of_stock", "stock_availability_contradiction"]
    assert notes(p5) == []
    # The flagged observation itself is untouched.
    assert p5.db.observations.find_one({"listing_id": "L-M", "source_timestamp": "2026-11-05T09:00:00"})["stock_quantity"] == 25


def test_paused_rules_are_not_replayed_when_resumed(p5):
    rule = make_rule(p5, T(1))
    rules.update_rule(p5.db, user_id="alice", rule_id=rule["id"], data={"enabled": False}, now=T(2))
    new_obs(p5, T(3), utc_row("L-F", "Flipkart", "1300", "60", 9))
    rules.update_rule(p5.db, user_id="alice", rule_id=rule["id"], data={"enabled": True}, now=T(4))
    p5.db.jobs.update_many({"type": "alerts"}, {"$set": {"status": "queued"}})
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(4))
    assert notes(p5) == []
    new_obs(p5, T(5), utc_row("L-F", "Flipkart", "1290", "60", 10))
    assert len(notes(p5)) == 1


def test_re_arm_and_cooldown(p5):
    rule = make_rule(p5, T(1), cooldown_hours=0)
    new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300", "60", 9))  # notified, disarmed
    new_obs(p5, T(3), utc_row("L-F", "Flipkart", "1290", "60", 10))  # qualifies but not armed
    new_obs(p5, T(4), utc_row("L-F", "Flipkart", "1400", "60", 11))  # above target: re-arms
    new_obs(p5, T(5), utc_row("L-F", "Flipkart", "1280", "60", 12))  # notified again
    outcomes = [e["outcome"] for e in sorted(events(p5, rule["id"]).values(), key=lambda e: e["evaluated_at"])]
    assert outcomes == ["notified", "suppressed_not_armed", "not_qualifying", "notified"]
    assert len(notes(p5)) == 2

    slow = make_rule(p5, T(6), cooldown_hours=24)
    new_obs(p5, T(7), utc_row("L-F", "Flipkart", "1270", "60", 13))  # notified
    new_obs(p5, T(8), utc_row("L-F", "Flipkart", "1400", "60", 14))  # re-arms
    new_obs(p5, T(9), utc_row("L-F", "Flipkart", "1260", "60", 15))  # within 24 h
    outcomes = [e["outcome"] for e in sorted(events(p5, slow["id"]).values(), key=lambda e: e["evaluated_at"])]
    assert outcomes == ["notified", "not_qualifying", "suppressed_cooldown"]
    # Manual re-arm is also possible.
    assert rules.update_rule(p5.db, user_id="alice", rule_id=rule["id"], data={"rearm": True}, now=T(10))["armed"] is True


def test_crash_between_steps_does_not_duplicate(p5):
    make_rule(p5, T(1))
    new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300", "60", 9))
    # Simulate a crash after the notification was written but before the event was recorded.
    p5.db.alert_events.delete_many({})
    p5.db.jobs.update_many({"type": "alerts"}, {"$set": {"status": "queued"}})
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(3))
    assert len(notes(p5)) == 1
    assert [e["outcome"] for e in p5.db.alert_events.find({})] == ["notified"]


def test_concurrent_evaluation_of_one_run_is_safe(p5):
    make_rule(p5, T(1))
    run = p5_import(p5.db, p5.settings, [utc_row("L-F", "Flipkart", "1300", "60", 9)], T(2), policy="require_utc")
    engine.evaluate_run(p5.db, run["_id"], now=T(2))
    engine.evaluate_run(p5.db, run["_id"], now=T(2))
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(2))
    assert len(notes(p5)) == 1


def test_each_user_gets_their_own_notification(p5):
    make_rule(p5, T(1), user="alice")
    make_rule(p5, T(1), user="bob")
    new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300", "60", 9))
    assert sorted(n["user_id"] for n in notes(p5)) == ["alice", "bob"]


def test_watch_period_end_stops_evaluation(p5):
    rule = make_rule(p5, T(1))
    p5.db.watchlist_items.update_one({"user_id": "alice", "product_id": "MCL0001"}, {"$set": {"horizon_date": "2026-11-05"}})
    new_obs(p5, T(2), utc_row("L-F", "Flipkart", "1300", "60", 9))  # ingested 6 Nov, after the horizon
    assert [e["reason"] for e in events(p5, rule["id"]).values()] == ["watch_period_ended"]
    assert notes(p5) == []


def test_evaluation_never_writes_source_data_or_other_workspaces(p5):
    make_rule(p5, T(1))
    before = [d for d in p5.db.observations.find({}).sort("_id", 1)]
    p5.db.jobs.update_many({"type": "alerts"}, {"$set": {"status": "queued"}})
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(2))
    assert [d for d in p5.db.observations.find({}).sort("_id", 1)] == before
    demo = p5.dbs[DataMode.DEMO]
    assert demo.notifications.count_documents({}) == 0 and demo.alert_events.count_documents({}) == 0


def test_stale_running_alert_jobs_are_requeued(p5):
    make_rule(p5, T(1))
    run = p5_import(p5.db, p5.settings, [utc_row("L-F", "Flipkart", "1300", "60", 9)], T(2), policy="require_utc")
    p5.db.jobs.update_one({"type": "alerts", "run_id": run["_id"]}, {"$set": {"status": "running", "started_at": T(2)}})
    assert engine.requeue_stale_alert_jobs(p5.db, now=T(3), older_than=timedelta(minutes=10)) == 1
    engine.process_alert_jobs(p5.db, now_fn=lambda: T(3))
    assert len(notes(p5)) == 1
