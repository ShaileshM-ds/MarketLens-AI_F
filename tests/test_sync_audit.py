"""Seller synchronization and dark-pattern audit (SCOPE §5): explicit cutoff, verified observations,
patterns worth investigating (never proof), rule version / severity / confidence / evidence / benign explanations."""

from datetime import datetime, timezone

import pytest

from conftest import p5_import, p5_row
from helpers import NOW
from marketlens_core.audit import product_audit
from marketlens_core.history import HistoryError
from marketlens_core.sync import product_sync
from test_evidence import END, day, row

pytestmark = pytest.mark.integration
UTC = timezone.utc
LATER = datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC)


def load(p5, rows, policy="require_utc"):
    p5_import(p5.db, p5.settings, rows, NOW, policy=policy, name=f"{policy}.csv")
    return p5


def steps(lid, market, change_days, n_days=80, offset=0, base=1000, **kw):
    """A price that alternates between base and base+100 at the given days-before-cutoff."""
    out, level = [], base
    for n in range(n_days - 1, -1, -1):
        if n + offset in change_days:
            level = base + 100 if level == base else base
        out.append(row(lid, market, level, 1500, n, urgency_message="", **kw))
    return out


def S(p5, cutoff=END, **kw):
    return product_sync(p5.db, "MCL0001", cutoff=cutoff, **{"window_days": 90, **kw})


def pair(s, a="L-A", b="L-F"):
    return next(p for p in s["pairs"] if {p["a"]["listing_id"], p["b"]["listing_id"]} == {a, b})


# ---------- seller synchronization ----------

def test_synchronized_changes_are_a_pattern_worth_investigating_not_proof(p5):
    days = {60, 50, 40, 30, 20}
    load(p5, steps("L-A", "Amazon", days) + steps("L-F", "Flipkart", days))
    s = S(p5)
    p = pair(s)
    assert s["status"] == "available" and p["status"] == "pattern"
    assert p["matched"] == 5 and p["same_day"] == 5 and len(p["matches"]) == 5
    assert p["a"]["seller_id"] != p["b"]["seller_id"] and p["a"]["marketplace"] != p["b"]["marketplace"]
    text = (p["summary"] + " " + s["note"]).lower()
    assert "not proof" in text and "collusion" not in text.replace("not proof of collusion", "")
    assert p["benign_explanations"]
    m = p["matches"][0]
    assert {"date_a", "date_b", "change_a_percent", "change_b_percent"} <= set(m)


def test_one_day_lag_is_matched_and_lead_is_reported(p5):
    days = {60, 50, 40, 30}
    load(p5, steps("L-A", "Amazon", days) + steps("L-F", "Flipkart", days, offset=-1))  # Flipkart moves a day later
    p = pair(S(p5))
    assert p["matched"] == 4 and p["same_day"] == 0 and p["a_first"] + p["b_first"] == 4


def test_independent_movements_and_similar_flat_prices(p5):
    load(p5, steps("L-A", "Amazon", {60, 40, 20}) + steps("L-F", "Flipkart", {55, 33, 12}))
    p = pair(S(p5))
    assert p["status"] == "independent" and p["matched"] == 0


def test_similar_prices_without_changes_are_not_synchronization(p5):
    load(p5, steps("L-A", "Amazon", set()) + steps("L-F", "Flipkart", set()))
    p = pair(S(p5))
    assert p["status"] == "no_changes" and "insufficient" in p["summary"].lower()


def test_sparse_currency_stale_and_leakage(p5):
    load(p5, steps("L-A", "Amazon", {60, 50, 40, 30, 3, 2}) + [row("L-F", "Flipkart", 1000, 1500, n) for n in range(0, 8)])
    assert pair(S(p5))["status"] == "insufficient"
    load(p5, [row("L-M", "Myntra", 12, 15, n, ship="1", currency="USD") for n in range(0, 80)])
    pm = pair(S(p5), "L-A", "L-M")
    assert pm["status"] == "not_comparable" and "currenc" in pm["summary"].lower()
    early = S(p5, cutoff=datetime.fromisoformat(f"{day(25)}T23:59:59+00:00"))
    assert all(m["date_a"] <= day(25) for p in early["pairs"] for m in p["matches"])
    assert all(e["date"] <= day(25) for p in early["pairs"] for e in p["a"]["changes"] + p["b"]["changes"])
    stale = S(p5, cutoff=LATER)
    assert all(p["status"] in ("insufficient", "not_comparable") for p in stale["pairs"])


def test_snapshot_only_sync_is_insufficient_and_api(p5):
    s = S(p5)
    assert s["status"] == "insufficient" and s["pairs"] == [] or all(p["status"] == "insufficient" for p in s["pairs"])
    q = {"mode": "imported", "cutoff": "2026-10-31T23:59:59Z", "window": 90}
    assert p5.anon.get("/api/v1/products/MCL0001/sync", params=q).status_code == 200
    assert p5.anon.get("/api/v1/products/MCL0001/sync", params={**q, "cutoff": "2026-10-31"}).status_code == 422
    assert p5.anon.get("/api/v1/products/MCL0001/sync", params={**q, "mode": "demo"}).status_code == 404
    with pytest.raises(HistoryError):
        S(p5, cutoff=datetime(2026, 10, 31))


# ---------- dark-pattern audit ----------

def A(p5, cutoff=END):
    return product_audit(p5.db, "MCL0001", cutoff=cutoff, window_days=90)


def finding(a, rule):
    return next((f for f in a["findings"] if f["rule_id"] == rule), None)


def test_reference_inflation_and_unsupported_discount_are_calculated_findings(p5):
    load(p5, [row("L-A", "Amazon", 1000, 1300 if n >= 30 else 1950, n, urgency_message="") for n in range(0, 90)])
    a = A(p5)
    ref, adv = finding(a, "reference_inflation"), finding(a, "unsupported_discount")
    assert ref and adv
    for f in (ref, adv):
        assert f["kind"] == "calculated" and f["rule_version"] and f["severity"] in ("low", "medium", "high")
        assert f["confidence"]["level"] in ("low", "medium", "high") and f["benign_explanations"] and f["supporting_observations"]
        assert "not a legal finding" in a["note"].lower()
    assert finding(a, "repeated_urgency") is None


def test_genuine_reduction_raises_no_price_findings(p5):
    load(p5, [row("L-A", "Amazon", 1000 + (n % 3) * 10, 1300, n, urgency_message="") for n in range(1, 60)] + [row("L-A", "Amazon", 800, 1300, 0, urgency_message="")])
    a = A(p5)
    assert finding(a, "reference_inflation") is None and finding(a, "unsupported_discount") is None


def test_urgency_is_flagged_only_when_repeated_while_stock_stays_normal(p5):
    load(p5, [row("L-A", "Amazon", 1000, 1300, n, urgency_message="Only a few left!", stock_quantity="40") for n in range(0, 30)])
    f = finding(A(p5), "repeated_urgency")
    assert f and f["kind"] == "heuristic" and f["severity"] == "low"
    assert "Only a few left!" in f["explanation"] and len(f["supporting_observations"]) <= 10


def test_urgency_consistent_with_low_stock_is_not_flagged(p5):
    load(p5, [row("L-A", "Amazon", 1000, 1300, n, urgency_message="Only 2 left!", availability="Limited Stock", stock_quantity="2") for n in range(0, 30)])
    a = A(p5)
    assert finding(a, "repeated_urgency") is None
    assert next(r for r in a["rules"] if r["rule_id"] == "repeated_urgency")["status"] == "not_triggered"


def test_stock_contradiction_on_snapshot_and_history_rules_disabled_without_history(p5):
    load(p5, [p5_row("L-A", "Amazon", "1380", "60", availability="Out of Stock", stock_quantity="5", timestamp="2026-11-05T09:00:00")], policy="allow_timezone_unknown")
    a = A(p5, cutoff=datetime(2026, 11, 6, 23, 59, 59, tzinfo=UTC))
    f = finding(a, "stock_contradiction")
    assert f and f["kind"] == "observed"
    assert f["supporting_observations"][0]["source_timestamp"] == "2026-11-05T09:00:00"
    rules = {r["rule_id"]: r for r in a["rules"]}
    assert rules["reference_inflation"]["status"] == "disabled" and "verified" in rules["reference_inflation"]["reason"].lower()
    assert rules["unsupported_discount"]["status"] == "disabled"
    # Snapshot rows ingested after the cutoff are never read.
    early = A(p5, cutoff=datetime(2026, 11, 1, tzinfo=UTC))
    assert finding(early, "stock_contradiction") is None


def test_audit_api_and_isolation(p5):
    q = {"mode": "imported", "cutoff": "2026-11-06T23:59:59Z", "window": 90}
    r = p5.anon.get("/api/v1/products/MCL0001/audit", params=q)
    assert r.status_code == 200 and {"findings", "rules", "note", "cutoff", "source"} <= set(r.json())
    assert p5.anon.get("/api/v1/products/MCL0001/audit", params={**q, "cutoff": "x"}).status_code == 422
    assert p5.anon.get("/api/v1/products/MCL0001/audit", params={**q, "mode": "demo"}).status_code == 404
