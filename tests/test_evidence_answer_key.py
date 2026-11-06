"""Evidence analytics evaluated against the Demo generator's separate answer key.

Only this test reads answer_key.json. The analytics never see it; they get the same Demo observations a
user would, with an explicit cutoff at the end of the generated period.
"""

import json
from datetime import datetime, timezone

import pytest

from helpers import NOW
from marketlens_core.demo import generator
from marketlens_core.evidence import price_evidence
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration
CUTOFF = datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def demo(mongo_client, tmp_path_factory):
    import uuid

    name = f"mltest_{uuid.uuid4().hex[:10]}_demo"
    db = mongo_client[name]
    out = tmp_path_factory.mktemp("export")
    generator.generate_demo(db, export_dir=out, now=NOW)
    key = json.loads((out / generator.KEY_FILE).read_text(encoding="utf-8"))
    yield db, key
    mongo_client.drop_database(name)


def scen(key, typ):
    return next(s for s in key["scenarios"] if s["type"] == typ)


def ev(db, pid, basis="base", window=90):
    return price_evidence(db, pid, cutoff=CUTOFF, window_days=window, basis=basis)


def test_genuine_discount(demo):
    db, key = demo
    s = scen(key, "genuine_discount")
    e = ev(db, s["product_ids"][0])
    d = e["detector"]
    assert d["verdict"] == "below_usual"
    assert d["savings_percent"] == pytest.approx(-s["expected"]["price_change_pct"], abs=5)
    assert d["reference"]["increased"] is False
    assert e["score"]["band"] in ("strong", "moderate")


def test_inflated_reference(demo):
    db, key = demo
    s = scen(key, "inflated_reference")
    d = ev(db, s["product_ids"][0])["detector"]
    assert d["verdict"] == "around_usual" and abs(d["savings_percent"]) < 5
    assert d["reference"]["increased"] is True
    assert d["reference"]["change_percent"] == pytest.approx(s["expected"]["reference_change_pct"], abs=5)
    assert d["advertised_support"] == "not_supported"
    assert ev(db, s["product_ids"][0])["score"]["band"] == "weak"


def test_stable_prices(demo):
    db, key = demo
    e = ev(db, scen(key, "stable_prices")["product_ids"][0])
    assert e["detector"]["verdict"] == "around_usual" and e["detector"]["savings_percent"] == 0
    assert e["detector"]["reference"]["increased"] is False and e["score"]["band"] == "weak"


def test_shipping_offset_shows_on_delivered_basis_only(demo):
    db, key = demo
    s = scen(key, "shipping_offset")
    base = ev(db, s["product_ids"][0], "base")["detector"]
    delivered = ev(db, s["product_ids"][0], "delivered")["detector"]
    assert base["savings_percent"] == pytest.approx(-s["expected"]["base_change_pct"], abs=4)
    assert abs(delivered["savings_percent"]) < 5 and delivered["verdict"] == "around_usual"


def test_insufficient_history(demo):
    db, key = demo
    e = ev(db, scen(key, "insufficient_history")["product_ids"][0])
    assert e["status"] == "insufficient" and e["score"]["status"] == "unavailable" and e["detector"] is None


def test_sparse_missing_days_are_disclosed(demo):
    db, key = demo
    s = scen(key, "sparse_missing_days")
    e = ev(db, s["product_ids"][0], window=180)
    assert e["status"] == "available"
    assert len(e["evidence"]["missing_dates"]) > 0
    assert any("missing" in x.lower() for x in e["limitations"])


def test_results_are_deterministic_and_synthetic(demo):
    db, key = demo
    pid = scen(key, "genuine_discount")["product_ids"][0]
    a, b = ev(db, pid), ev(db, pid)
    assert a == b and a["source"]["synthetic"] is True


def adv(db, pid, basis="base"):
    from marketlens_core.advice import buying_advice

    return buying_advice(db, pid, cutoff=CUTOFF, window_days=90, basis=basis)


def test_advice_against_the_answer_key(demo):
    db, key = demo
    g = adv(db, scen(key, "genuine_discount")["product_ids"][0])
    assert g["recommendation"]["code"] == "buy_now" and g["confidence"]["level"] in ("high", "medium")
    i = adv(db, scen(key, "inflated_reference")["product_ids"][0])
    assert i["recommendation"]["code"] == "consider_waiting" and i["confidence"]["level"] == "low"
    st = adv(db, scen(key, "stable_prices")["product_ids"][0])
    assert st["recommendation"]["code"] == "consider_waiting" and st["confidence"]["level"] == "low"  # a usual price is not a bargain
    sh = adv(db, scen(key, "shipping_offset")["product_ids"][0])
    assert "delivered_basis" in {s["key"] for s in sh["disagreeing"]}  # base drop offset by shipping
    assert adv(db, scen(key, "insufficient_history")["product_ids"][0])["recommendation"]["code"] == "insufficient_evidence"
    for a in (g, i, st, sh):
        assert a["forecast"]["used"] is False and a["source"]["synthetic"] is True


def test_future_price_memory_matches_planted_event_outcomes(demo):
    from datetime import date as _date

    from marketlens_core.forecast import product_forecast

    db, key = demo
    s = scen(key, "mixed_event_outcomes")
    f = product_forecast(db, s["product_ids"][0], cutoff=CUTOFF, basis="base")
    assert f["status"] == "available"
    found = {e["date"]: e for e in f["memory"]["events"]}
    for planted in s["expected"]["events"]:
        start = _date.fromisoformat(planted["start"])
        hit = next((found[d] for d in found if abs((_date.fromisoformat(d) - start).days) <= 1), None)
        assert hit is not None, planted["start"]
        assert hit["outcomes"]["7"]["outcome"] == planted["outcome_after_7_days"]


def test_walk_forward_forecasts_on_demo_history_are_honest(demo):
    from marketlens_core.forecast import product_forecast

    db, key = demo
    for typ in ("stable_prices", "genuine_discount", "mixed_event_outcomes"):
        f = product_forecast(db, scen(key, typ)["product_ids"][0], cutoff=CUTOFF, basis="base")
        for h in f["horizons"]:
            assert h["status"] == "available"
            m = {x["key"]: x for x in h["models"]}
            # The model is used only when it measurably beat the baseline; otherwise the baseline is used.
            # The candidate is used only when it beat the baseline by 5%+ in this series' own backtest.
            assert (h["chosen"] == "recent_median") == (h["improvement_percent"] >= 5)
            assert m["naive"]["n"] >= 20
    assert product_forecast(db, scen(key, "insufficient_history")["product_ids"][0], cutoff=CUTOFF)["status"] == "unavailable"


def test_audit_against_the_answer_key(demo):
    from marketlens_core.audit import product_audit

    db, key = demo

    def rules(typ):
        a = product_audit(db, scen(key, typ)["product_ids"][0], cutoff=CUTOFF, window_days=90)
        return {f["rule_id"] for f in a["findings"]}

    assert {"reference_inflation", "unsupported_discount"} <= rules("inflated_reference")
    assert "repeated_urgency" in rules("repeated_urgency")
    assert "reference_inflation" not in rules("genuine_discount") and "repeated_urgency" not in rules("genuine_discount")
    assert "repeated_urgency" not in rules("stable_prices")


def test_seller_sync_against_the_answer_key(demo):
    from marketlens_core.sync import product_sync

    db, key = demo
    mixed = product_sync(db, scen(key, "mixed_event_outcomes")["product_ids"][0], cutoff=CUTOFF, window_days=180)
    assert mixed["pairs"] and all(p["status"] == "pattern" for p in mixed["pairs"])  # planted store-wide events move every listing
    stable = product_sync(db, scen(key, "stable_prices")["product_ids"][0], cutoff=CUTOFF, window_days=180)
    assert all(p["status"] == "no_changes" for p in stable["pairs"])
    sw = scen(key, "seller_switch")
    s = product_sync(db, sw["product_ids"][0], cutoff=CUTOFF, window_days=90)
    amazon = next(p for p in s["pairs"] if {p["a"]["seller_id"], p["b"]["seller_id"]} == {sw["expected"]["cheapest_seller_before"], sw["expected"]["cheapest_seller_after"]})
    assert amazon["status"] != "pattern"  # the two sellers swap places: opposite moves are not synchronization
    assert product_sync(db, scen(key, "insufficient_history")["product_ids"][0], cutoff=CUTOFF, window_days=90)["status"] == "insufficient"
