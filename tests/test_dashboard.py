"""Analyst dashboard (SCOPE §5): database-backed aggregates, explicit UTC cutoff, workspace isolation,
snapshot vs verified separation, bounded and cached computation."""

from datetime import datetime, timezone

import pytest

from conftest import p5_import, p5_row
from helpers import NOW
from marketlens_core.dashboard import dashboard, dashboard_meta
from marketlens_core.demo import generator
from marketlens_core.history import HistoryError
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration
UTC = timezone.utc
CUT = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)


@pytest.fixture
def demo(p5, tmp_path):
    db = p5.dbs[DataMode.DEMO]
    generator.generate_demo(db, export_dir=tmp_path, now=NOW)
    import json

    key = json.loads((tmp_path / generator.KEY_FILE).read_text(encoding="utf-8"))
    return p5, db, key


def scen(key, typ):
    return next(s for s in key["scenarios"] if s["type"] == typ)["product_ids"][0]


def test_demo_aggregates_are_database_backed_and_link_to_products(demo):
    p5, db, key = demo
    d = dashboard(db, cutoff=CUT, window_days=90)
    t = d["totals"]
    assert t["products"] == db.products.count_documents({}) and t["listings"] == db.offers.count_documents({})
    assert t["verified_observations"] == db.observations.count_documents({"history_eligible": True, "observed_at": {"$lte": CUT}})
    assert t["snapshot_observations"] == 0 and d["provenance"]["synthetic"] is True
    h = d["historical"]
    assert h["status"] == "available" and h["products_analyzed"] == 39 and h["products_insufficient"] == 1
    assert sum(h["detector"].values()) == 39 and sum(h["advice"].values()) == 40
    assert scen(key, "inflated_reference") in {p["product_id"] for p in h["audit"]["by_rule"]["reference_inflation"]["products"]}
    assert scen(key, "mixed_event_outcomes") in {p["product_id"] for p in h["sync"]["pattern_products"]}
    assert {r["days"] for r in h["forecast"]["horizons"]} == {7, 14, 30}
    f7 = next(r for r in h["forecast"]["horizons"] if r["days"] == 7)
    assert f7["available"] == 39 and f7["mean_mae_baseline_minor"] > 0 and f7["mean_measured_coverage_percent"] is not None
    assert f7["coverage_note"].lower().startswith("nominal 80%")
    assert h["trend"] and all(p["date"] <= "2026-10-31" for p in h["trend"])
    assert {m["marketplace"] for m in d["marketplaces"]} == {"Amazon", "Flipkart", "Myntra"}
    row = next(r for r in h["products"] if r["product_id"] == scen(key, "genuine_discount"))
    assert row["verdict"] == "below_usual" and row["advice"] == "buy_now"


def test_cutoff_filters_and_cache(demo):
    p5, db, key = demo
    early = dashboard(db, cutoff=datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC), window_days=30)
    assert early["totals"]["verified_observations"] < dashboard(db, cutoff=CUT, window_days=30)["totals"]["verified_observations"]
    assert all(p["date"] <= "2026-07-31" for p in early["historical"]["trend"])
    cat = dashboard(db, cutoff=CUT, window_days=30, category="mobile-phones")
    assert cat["totals"]["products"] == db.products.count_documents({"category": "mobile-phones"})
    myn = dashboard(db, cutoff=CUT, window_days=30, marketplace="Myntra")
    assert {m["marketplace"] for m in myn["marketplaces"]} == {"Myntra"}
    assert all("clothing" in r["category"] for r in myn["historical"]["products"])
    again = dashboard(db, cutoff=CUT, window_days=30, category="mobile-phones")
    assert again["cache"]["hit"] is True and cat["cache"]["hit"] is False
    with pytest.raises(HistoryError):
        dashboard(db, cutoff=datetime(2026, 10, 31), window_days=30)


def test_snapshot_only_workspace_and_isolation(p5):
    load_flag = [p5_row("L-A", "Amazon", "1380", "60", availability="Out of Stock", stock_quantity="5", timestamp="2026-11-05T09:00:00")]
    p5_import(p5.db, p5.settings, load_flag, NOW, name="flag.csv")
    d = dashboard(p5.db, cutoff=datetime(2026, 11, 6, 23, 59, 59, tzinfo=UTC), window_days=90)
    assert d["totals"]["verified_observations"] == 0 and d["totals"]["snapshot_observations"] == 5
    assert d["historical"]["status"] == "no_verified_history" and d["historical"]["products"] == []
    assert d["quality"]["stock_contradiction_observations"] == 1
    assert d["provenance"]["synthetic"] is not True or d["provenance"]["synthetic_observations"] == 5
    meta = dashboard_meta(p5.db)
    assert meta["latest_verified_at"] is None and "mens-clothing" in meta["categories"]


def test_dashboard_api(demo):
    p5, db, key = demo
    m = p5.anon.get("/api/v1/dashboard/meta", params={"mode": "demo"}).json()
    assert m["latest_verified_at"].startswith("2026-10-31")
    q = {"mode": "demo", "cutoff": "2026-10-31T23:59:59Z", "window": 90}
    r = p5.anon.get("/api/v1/dashboard", params=q)
    assert r.status_code == 200 and r.json()["mode"] == "demo" and r.json()["totals"]["products"] == 40
    imp = p5.anon.get("/api/v1/dashboard", params={**q, "mode": "imported"}).json()
    assert imp["totals"]["products"] == 2  # workspaces never mix
    assert p5.anon.get("/api/v1/dashboard", params={**q, "cutoff": "2026-10-31"}).status_code == 422
    assert p5.anon.get("/api/v1/dashboard", params={k: v for k, v in q.items() if k != "cutoff"}).status_code == 422
    assert p5.anon.get("/api/v1/dashboard", params={**q, "mode": "live"}).status_code == 409
