"""Watchlist API: auth, merge-on-re-add, idempotent removal, ownership and workspace isolation."""

import pytest

pytestmark = pytest.mark.integration
W = "/api/v1/watchlist"


def test_signed_out_requests_are_refused(p5):
    for method, path in (("get", W), ("put", f"{W}/MCL0001"), ("delete", f"{W}/MCL0001"), ("get", "/api/v1/alerts"), ("get", "/api/v1/notifications"), ("get", "/api/v1/notifications/unread-count")):
        r = getattr(p5.anon, method)(path, params={"mode": "imported"})
        assert r.status_code == 401, (method, path)


def test_add_is_idempotent_and_re_add_merges_settings(p5):
    r = p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={"notes": "Gift idea", "horizon_date": "2026-12-31"})
    assert r.status_code == 200
    item = r.json()
    assert item["product_id"] == "MCL0001" and item["notes"] == "Gift idea" and item["horizon_date"] == "2026-12-31"
    r2 = p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={"notes": "Updated note"})
    assert r2.status_code == 200
    assert r2.json()["notes"] == "Updated note" and r2.json()["horizon_date"] == "2026-12-31"  # merged, not replaced
    assert p5.db.watchlist_items.count_documents({"user_id": "alice"}) == 1
    assert "user_product" in p5.db.watchlist_items.index_information()


def test_list_shows_product_pricing_and_alert_status(p5):
    p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={})
    items = p5.alice.get(W, params={"mode": "imported"}).json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["product"]["name"]
    assert it["product"]["pricing"]["lowest_listed"]["amount_minor"] == 137000
    assert it["product"]["pricing"]["lowest_confirmed_delivered"]["amount_minor"] == 143000
    assert it["product"]["availability_summary"]["in_stock"] == 3
    assert {q["code"] for q in it["product"]["quality_labels"]} >= {"synthetic_dataset", "timezone_unknown"}
    assert it["alerts"] == {"active": 0, "paused": 0}
    assert "_id" not in it and "user_id" not in it


def test_validation_and_missing_products(p5):
    assert p5.alice.put(f"{W}/NOPE", params={"mode": "imported"}, json={}).status_code == 404
    assert p5.alice.put(f"{W}/" + "x" * 200, params={"mode": "imported"}, json={}).status_code == 422
    assert p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={"notes": "x" * 501}).status_code == 422
    assert p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={"horizon_date": "2026-13-01"}).status_code == 422


def test_remove_is_idempotent_and_archives_its_rules(p5):
    p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={})
    rule = p5.alice.post("/api/v1/alerts", params={"mode": "imported"}, json={"product_id": "MCL0001", "target_price_minor": 140000, "currency": "INR", "basis": "base"}).json()
    assert p5.alice.delete(f"{W}/MCL0001", params={"mode": "imported"}).status_code == 204
    assert p5.alice.delete(f"{W}/MCL0001", params={"mode": "imported"}).status_code == 204
    assert p5.alice.get(W, params={"mode": "imported"}).json()["items"] == []
    stored = p5.db.alert_rules.find_one({"_id": rule["id"]})
    assert stored["status"] == "archived" and stored["enabled"] is False


def test_users_only_see_and_change_their_own_watchlist(p5):
    p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={"notes": "mine"})
    assert p5.bob.get(W, params={"mode": "imported"}).json()["items"] == []
    assert p5.bob.delete(f"{W}/MCL0001", params={"mode": "imported"}).status_code == 204  # removes nothing of alice's
    assert len(p5.alice.get(W, params={"mode": "imported"}).json()["items"]) == 1


def test_workspaces_are_isolated(p5):
    p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={})
    assert p5.alice.get(W, params={"mode": "demo"}).json()["items"] == []
    assert p5.alice.put(f"{W}/MCL0001", params={"mode": "demo"}, json={}).status_code == 404
    assert p5.alice.get(W, params={"mode": "live"}).status_code == 409
    assert p5.dbs[next(m for m in p5.dbs if m.value == "demo")].watchlist_items.count_documents({}) == 0


def test_cross_site_writes_are_blocked(p5):
    r = p5.alice.put(f"{W}/MCL0001", params={"mode": "imported"}, json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
