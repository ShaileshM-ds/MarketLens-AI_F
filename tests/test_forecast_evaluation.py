"""Forecast evaluation report on Demo history and the Methodology API (values come from the code)."""

from datetime import datetime, timezone

import pytest

from conftest import p5_import
from helpers import NOW
from marketlens_core import advice, audit, evidence, forecast, sync
from marketlens_core.alerts import signals
from marketlens_core.demo import generator
from marketlens_core.forecast import evaluation_report
from marketlens_core.history import HistoryError
from marketlens_core.settings import DataMode
from test_evidence import row

pytestmark = pytest.mark.integration
CUT = datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)


@pytest.fixture
def demo(p5, tmp_path):
    db = p5.dbs[DataMode.DEMO]
    generator.generate_demo(db, export_dir=tmp_path, now=NOW)
    return p5, db


def test_evaluation_report_on_demo(demo):
    p5, db = demo
    r = evaluation_report(db, cutoff=CUT, basis="base")
    assert r["synthetic"] is True and r["products_evaluated"] == 39 and r["listings_evaluated"] == 39
    assert [i["product_id"] for i in r["insufficient"]] == ["DEMO-P-011"]
    for h in r["horizons"]:
        assert h["days"] in (7, 14, 30) and h["points"] > 0
        assert h["first_origin"] <= h["last_origin"] <= "2026-10-31"
        assert h["mae_baseline_minor"] > 0 and h["mae_candidate_minor"] > 0
        for k in ("calibrated", "previous"):
            assert 0 <= h[k]["coverage_percent"] <= 100 and h[k]["mean_width_percent"] > 0 and h[k]["points"] > 0
    assert "not evidence of real-market performance" in r["note"].lower()
    early = evaluation_report(db, cutoff=datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc), basis="base")
    assert all(h["last_origin"] <= "2026-08-31" for h in early["horizons"])
    with pytest.raises(HistoryError):
        evaluation_report(db, cutoff=datetime(2026, 10, 31), basis="base")


def test_evaluation_keeps_currencies_and_listings_separate(p5):
    rows = [row("L-A", "Amazon", 1000 + (n % 5) * 10, 1300, n, urgency_message="") for n in range(0, 120)]
    rows += [row("L-A", "Amazon", 1000, 1300, n, urgency_message="") for n in ()]
    p5_import(p5.db, p5.settings, rows, NOW, policy="require_utc", name="a.csv")
    r = evaluation_report(p5.db, cutoff=CUT, basis="base")
    assert r["products_evaluated"] == 1 and r["listings"][0]["listing_id"] == "L-A"
    p5_import(p5.db, p5.settings, [row("L-F", "Flipkart", 12, 15, n, ship="1", currency="USD", urgency_message="") for n in range(0, 120)], NOW,
              policy="require_utc", name="usd.csv")
    r2 = evaluation_report(p5.db, cutoff=CUT, basis="base")
    assert r2["products_evaluated"] == 0 and "currenc" in r2["insufficient"][0]["reason"].lower()


def test_methodology_api_reports_the_constants_in_the_code(p5):
    m = p5.anon.get("/api/v1/methodology").json()
    assert m["evidence"]["min_days"] == evidence.MIN_DAYS and m["evidence"]["savings_threshold"] == evidence.SAVINGS_THRESHOLD
    assert m["evidence"]["weights"] == evidence.WEIGHTS and m["evidence"]["full_savings"] == evidence.FULL_SAVINGS
    assert m["advice"]["strong_savings"] == advice.STRONG_SAVINGS and m["advice"]["stale_days"] == advice.STALE_DAYS
    assert m["forecast"]["version"] == forecast.FORECAST_VERSION and m["forecast"]["horizons"] == list(forecast.HORIZONS)
    assert m["forecast"]["interval_method"] == "conformal-relative-abs"
    assert m["sync"]["change_percent"] == sync.CHANGE_PERCENT and m["audit"]["urgency_min_days"] == audit.URGENCY_MIN_DAYS
    assert set(m["alerts"]) == set(signals.TYPES) and len(m["alerts"]) == 8
    assert m["sections"] == ["ingestion", "history", "prices", "detector", "score", "advice", "forecast", "memory", "sync", "audit", "dashboard", "alerts"]


def test_forecast_evaluation_api(demo):
    p5, db = demo
    q = {"mode": "demo", "cutoff": "2026-10-31T23:59:59Z", "basis": "base"}
    r = p5.anon.get("/api/v1/forecast-evaluation", params=q)
    assert r.status_code == 200 and r.json()["products_evaluated"] == 39
    assert p5.anon.get("/api/v1/forecast-evaluation", params={**q, "cutoff": "2026-10-31"}).status_code == 422
    assert p5.anon.get("/api/v1/forecast-evaluation", params={**q, "mode": "imported"}).json()["products_evaluated"] == 0
