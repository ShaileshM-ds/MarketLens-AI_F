"""Alert rule API: validation, exact minor units, snapshot context without notifications, lifecycle, ownership."""

import pytest

pytestmark = pytest.mark.integration
A = "/api/v1/alerts"
Q = {"mode": "imported"}


def rule_body(**kw):
    return {"product_id": "MCL0001", "target_price_minor": 140000, "currency": "INR", "basis": "base", **kw}


def test_create_rule_adds_to_watchlist_and_shows_snapshot_only_as_context(p5):
    r = p5.alice.post(A, params=Q, json=rule_body())
    assert r.status_code == 201, r.text
    rule = r.json()
    assert len(rule["id"]) == 32
    for k, v in {"product_id": "MCL0001", "marketplace": None, "target_price_minor": 140000, "currency": "INR", "basis": "base",
                 "type": "below_target", "enabled": True, "armed": True, "cooldown_hours": 24, "status": "active",
                 "last_evaluated": None, "last_triggered_at": None}.items():
        assert rule[k] == v, k
    ctx = rule["current_context"]
    assert "context only" in ctx["note"].lower()
    assert {o["marketplace"] for o in ctx["qualifying_now"]} == {"Amazon", "Flipkart"}  # 1380 and 1370 <= 1400
    assert p5.db.notifications.count_documents({}) == 0  # never a retrospective notification
    assert p5.db.watchlist_items.count_documents({"user_id": "alice", "product_id": "MCL0001"}) == 1


def test_delivered_context_ignores_unknown_and_respects_store(p5):
    ctx = p5.alice.post(A, params=Q, json=rule_body(basis="delivered", marketplace="Myntra", target_price_minor=148000)).json()["current_context"]
    assert [(o["marketplace"], o["value_minor"]) for o in ctx["qualifying_now"]] == [("Myntra", 148000)]


@pytest.mark.parametrize(
    "patch,fragment",
    [
        ({"basis": "fastest"}, "basis"),
        ({"marketplace": "Etsy"}, "not sold"),
        ({"currency": "USD"}, "currency"),
        ({"currency": "XYZ"}, "currency"),
        ({"target_price_minor": 0}, "greater than"),
        ({"target_price_minor": -5}, "greater than"),
        ({"target_price_minor": 1.5}, "integer"),
        ({"type": "price_prophecy"}, "unknown alert type"),
        ({"cooldown_hours": 721}, "less than or equal"),
    ],
)
def test_rule_validation(p5, patch, fragment):
    r = p5.alice.post(A, params=Q, json=rule_body(**patch))
    assert r.status_code == 422, r.text
    assert fragment in r.text.lower()


def test_missing_product_and_other_workspace(p5):
    assert p5.alice.post(A, params=Q, json=rule_body(product_id="NOPE")).status_code == 404
    assert p5.alice.post(A, params={"mode": "demo"}, json=rule_body()).status_code == 404
    assert p5.alice.post(A, params={"mode": "live"}, json=rule_body()).status_code == 409


def test_list_edit_pause_resume_and_archive(p5):
    rule = p5.alice.post(A, params=Q, json=rule_body()).json()
    assert [x["id"] for x in p5.alice.get(A, params=Q).json()["rules"]] == [rule["id"]]
    r = p5.alice.patch(f"{A}/{rule['id']}", params=Q, json={"target_price_minor": 135000, "marketplace": "Amazon", "basis": "delivered"})
    assert r.status_code == 200 and (r.json()["target_price_minor"], r.json()["marketplace"], r.json()["basis"]) == (135000, "Amazon", "delivered")
    paused = p5.alice.patch(f"{A}/{rule['id']}", params=Q, json={"enabled": False}).json()
    assert paused["enabled"] is False
    resumed = p5.alice.patch(f"{A}/{rule['id']}", params=Q, json={"enabled": True}).json()
    assert resumed["enabled"] is True and resumed["armed"] is True
    assert resumed["active_since"] >= rule["active_since"]
    assert p5.alice.patch(f"{A}/{rule['id']}", params=Q, json={"marketplace": "Etsy"}).status_code == 422
    assert p5.alice.delete(f"{A}/{rule['id']}", params=Q).status_code == 204
    assert p5.alice.get(A, params=Q).json()["rules"] == []
    archived = p5.alice.get(A, params={**Q, "include_archived": "true"}).json()["rules"]
    assert archived[0]["status"] == "archived"
    assert p5.alice.patch(f"{A}/{rule['id']}", params=Q, json={"enabled": True}).status_code == 409


def test_rules_are_private(p5):
    rule = p5.alice.post(A, params=Q, json=rule_body()).json()
    assert p5.bob.get(A, params=Q).json()["rules"] == []
    assert p5.bob.patch(f"{A}/{rule['id']}", params=Q, json={"enabled": False}).status_code == 404
    assert p5.bob.delete(f"{A}/{rule['id']}", params=Q).status_code == 404
    assert p5.bob.get(f"{A}/{rule['id']}/events", params=Q).status_code == 404
    assert p5.alice.patch(f"{A}/not-a-rule-id", params=Q, json={"enabled": False}).status_code == 422
    assert p5.db.alert_rules.find_one({"_id": rule["id"]})["enabled"] is True
