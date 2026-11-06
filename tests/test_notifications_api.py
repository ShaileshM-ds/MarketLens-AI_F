"""Notifications API: owner-only, read/dismiss states, unread count, evidence, pagination."""

from datetime import timedelta

import pytest

from conftest import p5_import, p5_row
from helpers import NOW
from marketlens_core.alerts import engine, rules

pytestmark = pytest.mark.integration
N = "/api/v1/notifications"
Q = {"mode": "imported"}


@pytest.fixture
def notified(p5):
    rule = rules.create_rule(p5.db, user_id="alice", data={"product_id": "MCL0001", "target_price_minor": 135000, "currency": "INR", "basis": "base", "cooldown_hours": 0}, now=NOW + timedelta(hours=1))
    p5_import(p5.db, p5.settings, [p5_row("L-F", "Flipkart", "1300", "60", timestamp="2026-11-05T09:00:00Z")], NOW + timedelta(hours=2), policy="require_utc")
    engine.process_alert_jobs(p5.db, now_fn=lambda: NOW + timedelta(hours=2))
    return rule


def test_list_unread_count_and_evidence(p5, notified):
    body = p5.alice.get(N, params=Q).json()
    assert body["total"] == 1 and body["unread"] == 1
    n = body["items"][0]
    assert n["title"] == "New qualifying observation detected" and n["read"] is False
    assert (n["observed_minor"], n["target_minor"], n["basis"], n["marketplace"]) == (130000, 135000, "base", "Flipkart")
    assert n["email"] == {"status": "not_sent", "note": "Email delivery is not configured. This is a local outbox record; nothing was sent."}
    assert "_id" not in n and "user_id" not in n
    assert p5.alice.get(f"{N}/unread-count", params=Q).json() == {"unread": 1}
    detail = p5.alice.get(f"{N}/{n['id']}", params=Q).json()
    obs = detail["observation"]
    assert obs["price_minor"] == 130000 and obs["timestamp_quality"] == "utc" and obs["observed_at"].startswith("2026-11-05T09:00:00")
    assert detail["rule"]["id"] == notified["id"]
    events = p5.alice.get(f"/api/v1/alerts/{notified['id']}/events", params=Q).json()["items"]
    assert [e["outcome"] for e in events] == ["notified"] and events[0]["notification_id"] == n["id"]


def test_read_dismiss_and_read_all(p5, notified):
    nid = p5.alice.get(N, params=Q).json()["items"][0]["id"]
    assert p5.alice.post(f"{N}/{nid}/read", params=Q).json()["read"] is True
    assert p5.alice.get(f"{N}/unread-count", params=Q).json() == {"unread": 0}
    assert p5.alice.post(f"{N}/{nid}/dismiss", params=Q).json()["dismissed"] is True
    assert p5.alice.get(N, params=Q).json()["items"] == []
    assert len(p5.alice.get(N, params={**Q, "status": "all"}).json()["items"]) == 1
    assert p5.db.notifications.count_documents({}) == 1  # evidence kept
    # Read-all covers active (not dismissed) notifications: restore one to unread to check it.
    p5.db.notifications.update_one({"_id": nid}, {"$set": {"read_at": None, "dismissed_at": None}})
    assert p5.alice.post(f"{N}/read-all", params=Q).json() == {"marked_read": 1}


def test_notifications_are_private(p5, notified):
    nid = p5.alice.get(N, params=Q).json()["items"][0]["id"]
    assert p5.bob.get(N, params=Q).json()["total"] == 0
    assert p5.bob.get(f"{N}/{nid}", params=Q).status_code == 404
    assert p5.bob.post(f"{N}/{nid}/read", params=Q).status_code == 404
    assert p5.bob.post(f"{N}/{nid}/dismiss", params=Q).status_code == 404
    assert p5.bob.post(f"{N}/read-all", params=Q).json() == {"marked_read": 0}
    assert p5.db.notifications.find_one({"_id": nid})["read_at"] is None


def test_validation_pagination_and_workspace(p5, notified):
    assert p5.alice.get(N, params={**Q, "page_size": 101}).status_code == 422
    assert p5.alice.get(N, params={**Q, "page": 0}).status_code == 422
    assert p5.alice.get(N, params={**Q, "status": "weird"}).status_code == 422
    assert p5.alice.get(f"{N}/not-an-id", params=Q).status_code == 422
    assert p5.alice.get(N, params={"mode": "demo"}).json()["total"] == 0
    assert p5.alice.get(f"{N}/unread-count", params={"mode": "live"}).status_code == 409
