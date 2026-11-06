"""Buying advice (SCOPE §5): Buy now / Consider waiting / Insufficient evidence from observed history only."""

from datetime import datetime, timezone

import pytest

from conftest import p5_import
from helpers import NOW
from marketlens_core.advice import buying_advice, classify
from marketlens_core.history import HistoryError
from test_evidence import END, day, row

pytestmark = pytest.mark.integration


def load(p5, rows):
    p5_import(p5.db, p5.settings, rows, NOW, policy="require_utc", name="hist.csv")
    return p5


def A(p5, cutoff=END, **kw):
    return buying_advice(p5.db, "MCL0001", cutoff=cutoff, **{"window_days": 90, "basis": "base", **kw})


def usual(n_from=1, n_to=60, price=1000):
    return [row("L-A", "Amazon", price + (n % 3) * 10, 1300, n) for n in range(n_from, n_to)]


def test_classification_boundaries():
    assert classify(5.0, 50.0) == "buy_now"
    assert classify(20.0, 10.0) == "buy_now"            # a real reduction wins over a low percentile
    assert classify(4.99, 50.0) == "consider_waiting"   # an ordinary price is never presented as a bargain
    assert classify(4.99, 24.99) == "consider_waiting"
    assert classify(-5.0, 90.0) == "consider_waiting"


def test_buy_now_for_a_genuine_reduction_with_reasons_and_no_forecast(p5):
    a = A(load(p5, usual() + [row("L-A", "Amazon", 800, 1300, 0)]))
    assert a["recommendation"]["code"] == "buy_now"
    assert a["confidence"]["level"] == "high"
    assert a["price"]["current_minor"] == 80000 and a["price"]["usual_minor"] == 101000
    assert a["score"]["value"] is not None
    assert a["coverage"]["observed_days"] == 60 and a["freshness"]["age_hours"] == 13
    assert a["forecast"]["used"] is False and "not" in a["forecast"]["note"].lower()
    assert a["reasons"] and all("will" not in r.lower() for r in a["reasons"])  # no predictive claims
    assert a["cutoff"] == "2026-10-31T23:59:59Z"


def test_consider_waiting_when_above_usual(p5):
    a = A(load(p5, usual() + [row("L-A", "Amazon", 1150, 1300, 0)]))
    assert a["recommendation"]["code"] == "consider_waiting"
    assert any("above" in r.lower() for r in a["reasons"])


def test_usual_price_is_low_confidence_and_inflated_reference_is_a_disagreeing_signal(p5):
    rows = [row("L-A", "Amazon", 1000, 1300 if n >= 30 else 1950, n) for n in range(0, 90)]
    a = A(load(p5, rows))
    # Zero real savings behind an inflated reference: not a bargain. The misleading signals support waiting.
    assert a["recommendation"]["code"] == "consider_waiting" and a["confidence"]["level"] == "low"
    assert "not a bargain" in a["recommendation"]["reason"].lower()
    text = " ".join(a["reasons"]).lower()
    assert "reference price" in text and "advertised" in text
    assert a["disagreeing"] == []


def test_sparse_and_stale_data_lower_confidence_or_abstain(p5):
    rows = [row("L-A", "Amazon", 1000, 1300, n) for n in range(5, 60) if n % 2] + [row("L-A", "Amazon", 800, 1300, 4)]
    a = A(load(p5, rows))  # latest observation 4 days old, half the days missing
    assert a["recommendation"]["code"] == "buy_now"
    assert a["confidence"]["level"] in ("medium", "low")
    assert any("days old" in r for r in a["confidence"]["reasons"])
    assert any("missing" in r for r in a["confidence"]["reasons"])
    stale = A(p5, cutoff=datetime(2026, 11, 12, 23, 59, 59, tzinfo=timezone.utc))  # 12 days after the latest observation
    assert stale["recommendation"]["code"] == "insufficient_evidence" and "stale" in stale["recommendation"]["reason"].lower()


def test_insufficient_history_snapshot_only_and_mixed_currencies(p5):
    assert A(p5)["recommendation"]["code"] == "insufficient_evidence"  # snapshot only
    load(p5, [row("L-A", "Amazon", 1000, 1300, n) for n in range(0, 10)])
    a = A(p5)
    assert a["recommendation"]["code"] == "insufficient_evidence" and a["score"]["value"] is None
    load(p5, [row("L-F", "Flipkart", 12, 15, n, ship="1", currency="USD") for n in range(0, 30)])
    m = A(p5)
    assert m["recommendation"]["code"] == "insufficient_evidence"


def test_out_of_stock_current_everywhere_abstains(p5):
    rows = usual(1, 30) + [row("L-A", "Amazon", 700, 1300, 0, availability="Out of Stock", stock_quantity="0")]
    a = A(load(p5, rows))
    assert a["recommendation"]["code"] == "insufficient_evidence"


def test_cutoff_prevents_leakage(p5):
    load(p5, usual(5, 60) + [row("L-A", "Amazon", 500, 1300, n) for n in range(0, 5)])
    a = A(p5, cutoff=datetime.fromisoformat(f"{day(5)}T23:59:59+00:00"))
    # 1,020 on that day: within 5% of usual, but more than 75% of observed days were cheaper. The later 500s are never seen.
    assert a["price"]["current_minor"] == 102000 and a["recommendation"]["code"] == "consider_waiting"
    assert a["confidence"]["level"] == "low"
    assert "cheaper on more than 75%" in a["recommendation"]["reason"]  # the deciding signal leads
    with pytest.raises(HistoryError):
        A(p5, cutoff=datetime(2026, 10, 31))


def test_delivered_basis_disagreement_is_reported(p5):
    # Base price drops 10%, but shipping rises by the same amount: the delivered price doesn't fall.
    rows = usual(1, 60) + [row("L-A", "Amazon", 900, 1300, 0, ship="141")]
    a = A(load(p5, rows))
    assert a["recommendation"]["code"] == "buy_now"
    assert "delivered_basis" in {s["key"] for s in a["disagreeing"]}
    assert a["confidence"]["level"] != "high"


def test_api(p5):
    load(p5, usual() + [row("L-A", "Amazon", 800, 1300, 0)])
    q = {"mode": "imported", "cutoff": "2026-10-31T23:59:59Z", "window": 90, "basis": "base"}
    r = p5.anon.get("/api/v1/products/MCL0001/advice", params=q)
    assert r.status_code == 200
    j = r.json()
    for k in ("recommendation", "confidence", "reasons", "disagreeing", "signals", "price", "score", "coverage", "freshness",
              "limitations", "source", "window", "cutoff", "method", "forecast"):
        assert k in j, k
    assert p5.anon.get("/api/v1/products/MCL0001/advice", params={**q, "cutoff": "2026-10-31"}).status_code == 422
    assert p5.anon.get("/api/v1/products/MCL0001/advice", params={**q, "window": 45}).status_code == 422
    assert p5.anon.get("/api/v1/products/NOPE/advice", params=q).status_code == 404
