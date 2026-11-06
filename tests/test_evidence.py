"""Real Price Detector and Genuine Discount Score (SCOPE §5): explicit cutoff, verified observations only."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import p5_import, p5_row
from helpers import NOW
from marketlens_core.evidence import MIN_DAYS, price_evidence, score_components
from marketlens_core.history import HistoryError

pytestmark = pytest.mark.integration
UTC = timezone.utc
END = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)


def day(n):  # n days before 31 Oct
    return (datetime(2026, 10, 31, tzinfo=UTC) - timedelta(days=n)).date().isoformat()


def row(lid, market, price, ref, n, hour=10, ship="40", **kw):
    disc = f"{(ref - price) / ref * 100:.2f}"
    return p5_row(lid, market, str(price), ship, original_price=str(ref), discount=disc, timestamp=f"{day(n)}T{hour:02d}:00:00Z", **kw)


def load(p5, rows):
    p5_import(p5.db, p5.settings, rows, NOW, policy="require_utc", name="hist.csv")
    return p5


def E(p5, cutoff=END, **kw):
    return price_evidence(p5.db, "MCL0001", cutoff=cutoff, **{"window_days": 90, "basis": "base", **kw})


def test_genuine_reduction_is_measured_against_the_median_excluding_the_current_observation(p5):
    rows = [row("L-A", "Amazon", 1000 + (n % 3) * 10, 1300, n) for n in range(1, 60)]  # usual: 1000/1010/1020, median 1010
    rows.append(row("L-A", "Amazon", 800, 1300, 0))  # current
    e = E(load(p5, rows))
    d = e["detector"]
    assert e["status"] == "available" and e["cutoff"] == "2026-10-31T23:59:59Z"
    assert e["headline"]["listing_id"] == "L-A"
    assert d["current_minor"] == 80000 and d["baseline_minor"] == 101000
    assert d["savings_percent"] == pytest.approx(20.79, abs=0.01)  # 100 x (1010 - 800) / 1010
    assert d["verdict"] == "below_usual"
    # Advertised 38.46% vs 20.79% real: the reduction is real but smaller than advertised.
    assert d["advertised_discount_percent"] == pytest.approx(38.46, abs=0.01)
    assert d["advertised_support"] == "partly_supported"
    assert d["reference"]["increased"] is False
    s = e["score"]
    assert s["status"] == "available" and 0 <= s["value"] <= 100
    assert {c["key"]: c["weight"] for c in s["components"]} == {"savings": 60, "percentile": 25, "agreement": 15}
    assert next(c for c in s["components"] if c["key"] == "percentile")["value"] == 100  # cheaper than every baseline day
    ev = e["evidence"]
    assert ev["current_observation"]["observed_at"].startswith(day(0)) and ev["current_observation"]["marketplace"] == "Amazon"
    assert len(ev["daily"]) == 59 and all(p["date"] < day(0) for p in ev["daily"])
    assert e["source"]["source_labels"] and e["source"]["ingestion_runs"] and e["window"]["days"] == 90


def test_inflated_reference_without_price_change_is_flagged(p5):
    rows = [row("L-A", "Amazon", 1000, 1300 if n >= 30 else 1950, n) for n in range(0, 90)]
    e = E(load(p5, rows))
    d = e["detector"]
    assert d["savings_percent"] == 0 and d["verdict"] == "around_usual"
    assert d["advertised_support"] == "not_supported"
    ref = d["reference"]
    assert ref["increased"] is True and ref["change_percent"] == pytest.approx(50.0)
    assert ref["since"] == day(29)
    assert e["score"]["value"] < 40 and e["score"]["band"] == "weak"


def test_stable_prices_and_price_above_usual_stay_visible(p5):
    rows = [row("L-A", "Amazon", 1000, 1300, n) for n in range(1, 40)] + [row("L-A", "Amazon", 1100, 1300, 0)]
    d = E(load(p5, rows))["detector"]
    assert d["savings_percent"] == -10.0 and d["verdict"] == "above_usual"  # negative results stay visible


def test_insufficient_days_returns_insufficient_evidence(p5):
    rows = [row("L-A", "Amazon", 1000, 1300, n) for n in range(0, MIN_DAYS - 1)]
    e = E(load(p5, rows))
    assert e["status"] == "insufficient" and e["detector"] is None
    assert e["score"]["status"] == "unavailable" and e["score"]["value"] is None
    assert "Insufficient historical evidence" in e["reason"]


def test_snapshot_only_product_is_unavailable_and_timezone_unknown_is_excluded(p5):
    e = E(p5)  # p5 holds only timezone-unknown snapshot rows
    assert e["status"] == "unavailable" and e["detector"] is None and e["score"]["value"] is None
    assert e["excluded"]["timezone_unknown"] == 3


def test_missing_days_are_disclosed_and_never_filled(p5):
    rows = [row("L-A", "Amazon", 1000, 1300, n) for n in range(0, 40) if n % 3 != 1]
    e = E(load(p5, rows))
    assert e["status"] == "available"
    assert e["evidence"]["missing_dates"] and day(1) in e["evidence"]["missing_dates"]
    assert all(p["date"] not in e["evidence"]["missing_dates"] for p in e["evidence"]["daily"])
    assert any("missing" in lim.lower() for lim in e["limitations"])


def test_cutoff_is_enforced_and_later_data_never_leaks(p5):
    rows = [row("L-A", "Amazon", 1000, 1300, n) for n in range(5, 60)] + [row("L-A", "Amazon", 500, 1300, n) for n in range(0, 5)]
    load(p5, rows)
    cut = datetime.fromisoformat(f"{day(5)}T23:59:59+00:00")
    e = E(p5, cutoff=cut)
    assert e["detector"]["current_minor"] == 100000 and e["detector"]["savings_percent"] == 0
    assert all(p["date"] <= day(5) for p in e["evidence"]["daily"])
    assert e["evidence"]["current_observation"]["observed_at"].startswith(day(5))
    with pytest.raises(HistoryError):
        E(p5, cutoff=datetime(2026, 10, 31))  # naive cutoff refused
    with pytest.raises(HistoryError):
        E(p5, window_days=45)


def test_out_of_stock_current_and_unknown_shipping_are_not_used(p5):
    rows = [row("L-A", "Amazon", 1000, 1300, n) for n in range(1, 30)]
    rows.append(row("L-A", "Amazon", 700, 1300, 0, availability="Out of Stock", stock_quantity="0"))
    rows += [row("L-F", "Flipkart", 1050, 1300, n, ship="" if n == 0 else "40") for n in range(0, 30)]
    load(p5, rows)
    e = E(p5)
    by = {x["listing_id"]: x for x in e["listings"]}
    assert by["L-A"]["status"] == "unavailable" and "out of stock" in by["L-A"]["reason"].lower()
    assert e["headline"]["listing_id"] == "L-F"  # the out-of-stock 700 is never the "current" price
    dl = E(p5, basis="delivered")
    f = next(x for x in dl["listings"] if x["listing_id"] == "L-F")
    assert f["status"] == "unavailable" and "Total incomplete" in f["reason"]  # unknown shipping is never free
    assert dl["excluded"]["unknown_shipping"] >= 1


def test_mixed_currencies_are_not_compared(p5):
    rows = [row("L-A", "Amazon", 1000, 1300, n) for n in range(0, 30)]
    rows += [row("L-F", "Flipkart", 12, 15, n, ship="1", currency="USD") for n in range(0, 30)]
    e = E(load(p5, rows))
    assert e["status"] == "unavailable" and e["headline"] is None
    assert "currenc" in e["reason"].lower()
    assert all(x["status"] == "available" for x in e["listings"] if x["listing_id"] in ("L-A", "L-F"))


def test_score_formula_boundaries_and_determinism():
    top = score_components(savings=40.0, percentile=100.0, advertised=40.0)
    assert top["value"] == 100 and top["weight_used"] == 100
    zero = score_components(savings=-12.0, percentile=0.0, advertised=60.0)
    assert zero["value"] == 0
    no_adv = score_components(savings=12.5, percentile=50.0, advertised=None)
    agreement = next(c for c in no_adv["components"] if c["key"] == "agreement")
    assert agreement["available"] is False and no_adv["weight_used"] == 85
    assert no_adv["value"] == round((60 * 50 + 25 * 50) / 85)  # 50 = 12.5 / 25 x 100; disclosed reweighting
    mid = score_components(savings=10.0, percentile=60.0, advertised=25.0)
    assert mid == score_components(savings=10.0, percentile=60.0, advertised=25.0)
    assert next(c for c in mid["components"] if c["key"] == "agreement")["value"] == 50  # gap 15 -> halfway between 5 and 25


def test_api_shape_validation_and_workspace_isolation(p5):
    load(p5, [row("L-A", "Amazon", 1000, 1300, n) for n in range(0, 30)])
    q = {"mode": "imported", "cutoff": "2026-10-31T23:59:59Z", "window": 90, "basis": "base"}
    r = p5.anon.get("/api/v1/products/MCL0001/evidence", params=q)
    assert r.status_code == 200
    j = r.json()
    for k in ("detector", "score", "evidence", "source", "window", "cutoff", "limitations", "method", "listings", "excluded"):
        assert k in j, k
    assert j["mode"] == "imported"
    assert p5.anon.get("/api/v1/products/MCL0001/evidence", params={**q, "cutoff": "2026-10-31T23:59:59"}).status_code == 422
    assert p5.anon.get("/api/v1/products/MCL0001/evidence", params={k: v for k, v in q.items() if k != "cutoff"}).status_code == 422
    assert p5.anon.get("/api/v1/products/MCL0001/evidence", params={**q, "mode": "demo"}).status_code == 404
