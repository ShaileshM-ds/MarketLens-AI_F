"""Forecasting and Future Price Memory (SCOPE §5): chronological backtests against a baseline, measured
interval coverage, fallback to the baseline, and completed outcomes after similar past events."""

from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import p5_import
from helpers import NOW
from marketlens_core.forecast import HORIZONS, backtest, evaluate, listing_series, price_memory, product_forecast
from marketlens_core.history import HistoryError
from test_evidence import END, day, row

UTC = timezone.utc
D0 = date(2026, 5, 1)


def series(values, start=D0, skip=()):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values) if i not in skip]


def spiky(n=150):
    # Usual price 1000; every 5th day a one-day 30% sale. The last price is often misleading; the median isn't.
    return [70000 if i % 5 == 0 else 100000 for i in range(n)]


# ---- pure functions: no database ----

def test_backtest_is_chronological_and_never_uses_later_data():
    s = series(spiky())
    bt = backtest(s, 7, "naive")
    assert [b["origin"] for b in bt] == sorted(b["origin"] for b in bt)
    assert all(b["target"] == b["origin"] + timedelta(days=7) for b in bt)
    # Changing values after an origin never changes that origin's prediction.
    changed = s[:100] + [(d, 1) for d, _ in s[100:]]
    bt2 = {b["origin"]: b["pred"] for b in backtest(changed, 7, "recent_median")}
    for b in backtest(s, 7, "recent_median"):
        if b["origin"] < s[100][0]:
            assert bt2[b["origin"]] == b["pred"]


def test_model_beats_baseline_on_mean_reverting_prices_and_reports_metrics():
    ev = evaluate(series(spiky()), 7)
    m = {x["key"]: x for x in ev["models"]}
    assert m["recent_median"]["mae_minor"] < m["naive"]["mae_minor"]
    assert ev["chosen"] == "recent_median" and ev["status"] == "available"
    assert ev["improvement_percent"] > 5
    assert m["naive"]["n"] == m["recent_median"]["n"] >= 20
    assert {"mae_minor", "mape_percent", "n"} <= set(m["naive"])
    f = ev["forecast"]
    assert f["value_minor"] == 100000 and f["date"] == (D0 + timedelta(days=149 + 7)).isoformat()
    assert f["low_minor"] <= f["value_minor"] <= f["high_minor"]
    assert 0 <= f["interval"]["measured_coverage_percent"] <= 100 and f["interval"]["level_percent"] == 80


def test_falls_back_to_baseline_when_the_model_does_not_improve():
    # Steady decline: the last price is the better guess; the median lags.
    ev = evaluate(series([200000 - 500 * i for i in range(150)]), 14)
    assert ev["chosen"] == "naive" and "baseline" in ev["note"].lower()
    flat = evaluate(series([100000] * 120), 30)
    assert flat["chosen"] == "naive"  # no improvement over a perfect baseline
    assert flat["forecast"]["value_minor"] == 100000


def test_all_horizons_deterministic_and_insufficient_when_too_few_origins():
    s = series(spiky(60))
    a = [evaluate(s, h) for h in HORIZONS]
    assert a == [evaluate(s, h) for h in HORIZONS]
    assert HORIZONS == (7, 14, 30)
    short = series(spiky(40))
    assert evaluate(short, 7)["status"] == "available"
    r30 = evaluate(short, 30)
    assert r30["status"] == "insufficient" and r30["forecast"] is None and "backtest" in r30["reason"].lower()


def test_missing_dates_are_skipped_never_filled():
    s = series(spiky(150), skip={i for i in range(150) if i % 7 == 3})
    bt = backtest(s, 7, "naive")
    have = {d for d, _ in s}
    assert all(b["target"] in have and b["origin"] in have for b in bt)


def test_future_price_memory_completed_non_overlapping_outcomes():
    v = [100000] * 200
    for start, stay in ((40, 7), (80, 21), (120, 7), (190, 10)):
        for i in range(start, min(200, start + stay)):
            v[i] = 85000
    mem = price_memory(series(v))
    starts = [e["date"] for e in mem["events"]]
    assert starts == [(D0 + timedelta(days=d)).isoformat() for d in (40, 80, 120, 190)]
    e40 = mem["events"][0]["outcomes"]
    assert e40["7"]["outcome"] == "returned" and e40["3"]["outcome"] == "stayed_low"
    assert mem["events"][1]["outcomes"]["7"]["outcome"] == "stayed_low"
    assert mem["events"][3]["outcomes"]["14"]["outcome"] == "not_completed"  # 190 + 14 is after the last day
    s7 = mem["summary"]["7"]
    assert s7["completed"] == 4 and s7["returned"] == 2 and s7["stayed_low"] == 2
    assert "probab" not in mem["note"].lower() or "not a probability" in mem["note"].lower()
    assert mem["current_event"] is not None  # the latest day is inside a similar drop


# ---- database-backed ----

def load(p5, rows):
    p5_import(p5.db, p5.settings, rows, NOW, policy="require_utc", name="hist.csv")
    return p5


def F(p5, cutoff=END, basis="base"):
    return product_forecast(p5.db, "MCL0001", cutoff=cutoff, basis=basis)


@pytest.mark.integration
def test_product_forecast_uses_only_data_up_to_the_cutoff(p5):
    rows = [row("L-A", "Amazon", 700 if n % 5 == 0 else 1000, 1300, n) for n in range(5, 120)]
    rows += [row("L-A", "Amazon", 300, 1300, n) for n in range(0, 5)]  # after the cutoff below
    load(p5, rows)
    cut = datetime.fromisoformat(f"{day(5)}T23:59:59+00:00")
    f = F(p5, cut)
    assert f["status"] == "available" and f["cutoff"] == f"{day(5)}T23:59:59Z"
    assert all(p["date"] <= day(5) for p in f["history"])
    h7 = next(h for h in f["horizons"] if h["days"] == 7)
    assert h7["forecast"]["value_minor"] in (70000, 100000)
    assert h7["forecast"]["date"] == (date.fromisoformat(day(5)) + timedelta(days=7)).isoformat()
    assert f["source"]["synthetic"] is True and f["predicted_values_are_observations"] is False
    assert {"memory", "coverage", "freshness", "limitations", "method", "headline"} <= set(f)


@pytest.mark.integration
def test_snapshot_insufficient_stale_and_mixed_currency_are_unavailable(p5):
    assert F(p5)["status"] == "unavailable"  # snapshot only
    load(p5, [row("L-A", "Amazon", 1000, 1300, n) for n in range(0, 10)])
    assert F(p5)["status"] == "unavailable"
    load(p5, [row("L-A", "Amazon", 1000, 1300, n) for n in range(10, 120)])
    stale = F(p5, datetime(2026, 11, 20, 23, 59, 59, tzinfo=UTC))
    assert stale["status"] == "unavailable" and "stale" in stale["reason"].lower()
    load(p5, [row("L-F", "Flipkart", 12, 15, n, ship="1", currency="USD") for n in range(0, 30)])
    assert F(p5)["status"] == "unavailable"


@pytest.mark.integration
def test_unknown_shipping_never_becomes_a_delivered_forecast(p5):
    load(p5, [row("L-A", "Amazon", 1000, 1300, n, ship="") for n in range(0, 120)])
    assert F(p5, basis="delivered")["status"] == "unavailable"
    assert F(p5, basis="base")["status"] == "available"


@pytest.mark.integration
def test_api_and_advice_integration(p5):
    load(p5, [row("L-A", "Amazon", 700 if n % 5 == 0 else 1000, 1300, n) for n in range(1, 150)] + [row("L-A", "Amazon", 1000, 1300, 0)])
    q = {"mode": "imported", "cutoff": "2026-10-31T23:59:59Z", "basis": "base"}
    r = p5.anon.get("/api/v1/products/MCL0001/forecast", params=q)
    assert r.status_code == 200 and len(r.json()["horizons"]) == 3
    assert p5.anon.get("/api/v1/products/MCL0001/forecast", params={**q, "cutoff": "2026-10-31"}).status_code == 422
    assert p5.anon.get("/api/v1/products/NOPE/forecast", params=q).status_code == 404
    a = p5.anon.get("/api/v1/products/MCL0001/advice", params={**q, "window": 90}).json()
    fc = a["forecast"]
    assert fc["used"] is False  # never changes the historical recommendation
    assert fc["expectation"] is not None and fc["expectation"]["horizon_days"] == 7
    assert fc["expectation"]["model"] != "naive" and fc["expectation"]["mae_minor"] < fc["expectation"]["baseline_mae_minor"]
    assert "not a guarantee" in fc["expectation"]["note"].lower()


# ---- interval calibration (forecast-2): split-conformal on relative absolute errors, walk-forward ----

from marketlens_core.forecast import conformal_quantile, walk_forward_intervals  # noqa: E402


def test_conformal_quantile_uses_the_finite_sample_rank():
    xs = [0.01 * i for i in range(1, 11)]  # 10 residuals
    assert conformal_quantile(xs, 0.8) == pytest.approx(0.09)  # rank ceil(11 x 0.8) = 9
    assert conformal_quantile(xs[:3], 0.8) is None  # rank 4 > 3: too few residuals for an 80% interval
    assert conformal_quantile([], 0.8) is None


def test_walk_forward_intervals_use_only_errors_known_before_each_origin():
    s = series(spiky(150))
    bt = backtest(s, 7, "naive")
    wf = walk_forward_intervals(bt)
    for p in wf["points"]:
        assert all(t <= p["origin"] for t in p["known_targets"])  # no future evaluation errors
    # Changing late actual prices never changes intervals built at earlier origins.
    cut = bt[60]["origin"]
    bt2 = [dict(b, actual=b["actual"] * 3) if b["target"] > cut else b for b in bt]
    early = {p["origin"]: (p["low"], p["high"]) for p in walk_forward_intervals(bt2)["points"] if p["origin"] <= cut}
    assert early == {p["origin"]: (p["low"], p["high"]) for p in wf["points"] if p["origin"] <= cut}


def test_coverage_and_width_are_measured_together():
    # Deterministic noise around a flat price: errors are exchangeable, so coverage should be near the target.
    noise = [((i * 37) % 21 - 10) * 200 for i in range(200)]
    wf = walk_forward_intervals(backtest(series([100000 + n for n in noise]), 7, "naive"))
    assert 70 <= wf["coverage_percent"] <= 95
    assert wf["mean_width_percent"] > 0 and wf["n"] >= 20
    flat = walk_forward_intervals(backtest(series([100000] * 120), 7, "naive"))
    assert flat["coverage_percent"] == 100 and flat["mean_width_percent"] == 0  # zero width is honest for a constant price


def test_evaluate_reports_calibrated_and_previous_intervals():
    ev = evaluate(series(spiky()), 14)
    it = ev["forecast"]["interval"]
    assert it["method"] == "conformal-relative-abs" and it["level_percent"] == 80
    assert {"measured_coverage_percent", "mean_width_percent", "measured_on"} <= set(it)
    prev = it["previous_method"]
    assert {"measured_coverage_percent", "mean_width_percent"} <= set(prev)
    f = ev["forecast"]
    assert f["low_minor"] <= f["value_minor"] <= f["high_minor"]


def test_too_few_errors_gives_no_interval():
    ev = evaluate(series(spiky(40)), 7)  # 20 backtest points but very few errors known at the end of each origin
    f = ev["forecast"]
    assert f is not None and ev["status"] == "available"
    assert (f["low_minor"] is None) == (f["interval"]["half_width_percent"] is None)


@pytest.mark.integration
def test_model_selection_is_per_series_and_never_leaks_across_series(p5):
    # MCL0001 / L-A: one-day sales, so the 14-day median beats the last price for this series.
    # MCL0002 / L-2A: a steady decline, where the last price is far better.
    # Each series is judged only on its own backtest: neither result changes the other's choice.
    rows = [row("L-A", "Amazon", 700 if n % 5 == 0 else 1000, 1300, n, urgency_message="") for n in range(1, 150)] + [row("L-A", "Amazon", 1000, 1300, 0, urgency_message="")]
    rows += [row("L-2A", "Amazon", 1000 + 50 * n, 9000, n, pid="MCL0002", product_name="Other product", urgency_message="") for n in range(0, 150)]
    load(p5, rows)
    a = next(h for h in F(p5)["horizons"] if h["days"] == 7)
    b = next(h for h in product_forecast(p5.db, "MCL0002", cutoff=END, basis="base")["horizons"] if h["days"] == 7)
    assert a["chosen"] == "recent_median" and a["improvement_percent"] >= 5
    assert b["chosen"] == "naive" and b["improvement_percent"] < 5
    # The same series alone gives the same choice: the other series has no influence.
    alone = evaluate(listing_series(p5.db, "L-A", cutoff=END, basis="base")[0], 7)
    assert alone["chosen"] == a["chosen"] and alone["models"] == a["models"]
    adv = p5.anon.get("/api/v1/products/MCL0002/advice", params={"mode": "imported", "cutoff": "2026-10-31T23:59:59Z"}).json()
    assert adv["forecast"]["expectation"] is None  # MCL0002's baseline wins, so no candidate-based expectation
    from marketlens_core.forecast import evaluation_report

    r = evaluation_report(p5.db, cutoff=END, basis="base")
    e7 = next(h for h in r["horizons"] if h["days"] == 7)
    assert e7["candidate_chosen"] == 1 and e7["baseline_chosen"] == 1  # one series each, chosen independently
