"""Explorer edge cases with small purpose-built files (real MongoDB, throwaway databases)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from helpers import SAMPLE_ROW, csv_bytes
from marketlens_core.explorer import rebuild_product_summaries
from marketlens_core.settings import DataMode
from test_importer_db import run_import

pytestmark = pytest.mark.integration
API = "/api/v1/products"


def row(listing, marketplace, **kw):
    return {**SAMPLE_ROW, "listing_id": listing, "marketplace": marketplace, "seller_id": f"S-{listing}", **kw}


@pytest.fixture
def client(settings, dbs):
    with TestClient(create_app(settings)) as c:
        yield c


def detail(client, pid="MCL0001"):
    return client.get(f"{API}/{pid}", params={"mode": "imported"}).json()


def listing(client, **params):
    return client.get(API, params={"mode": "imported", **params}).json()


def test_unknown_shipping_is_never_free_or_total(dbs, settings, client):
    rows = [row("L-A", "Amazon", shipping_cost=""), row("L-B", "Flipkart", shipping_cost="0", price="1500")]
    run_import(dbs[DataMode.IMPORTED], settings, "a.csv", csv_bytes(rows))
    d = detail(client)
    a = next(o for o in d["offers"] if o["listing_id"] == "L-A")
    assert a["shipping_known"] is False and a["shipping_minor"] is None and a["total_minor"] is None
    assert a["free_shipping"] is False
    assert d["comparison"]["offers_with_unknown_shipping"] == 1
    assert d["comparison"]["lowest_delivered_price_minor"] == 150000  # only the known one
    assert "unknown shipping" in d["comparison"]["note"].lower()
    item = listing(client)["items"][0]
    assert item["lowest_price"]["amount_minor"] == 138000
    assert item["lowest_price"]["offers_with_unknown_shipping"] == 1
    assert listing(client, free_shipping="true", marketplace="Amazon")["total"] == 0


def test_small_amounts_and_conditional_offers(dbs, settings, client):
    rows = [row("L-A", "Amazon", price="0.29", original_price="1", shipping_cost="0.01", coupon_discount="0.20", discount="71")]
    run_import(dbs[DataMode.IMPORTED], settings, "a.csv", csv_bytes(rows))
    o = detail(client)["offers"][0]
    assert (o["price_minor"], o["shipping_minor"], o["total_minor"], o["coupon_discount_minor"]) == (29, 1, 30, 20)
    assert listing(client)["items"][0]["lowest_price"]["amount_minor"] == 29


def test_different_currencies_are_never_mixed(dbs, settings, client):
    rows = [row("L-A", "Amazon"), row("L-B", "Flipkart", currency="USD", price="10")]
    run_import(dbs[DataMode.IMPORTED], settings, "a.csv", csv_bytes(rows))
    d = detail(client)
    assert d["comparison"]["lowest_base_price_minor"] is None
    assert "currenc" in d["comparison"]["note"].lower()
    assert not any(o["is_lowest_base"] for o in d["offers"])
    item = listing(client)["items"][0]
    assert item["lowest_price"] is None and "currenc" in item["lowest_price_unavailable_reason"].lower()
    usd = listing(client, currency="USD", price_min_minor=1000, price_max_minor=1000)
    assert usd["total"] == 1 and usd["items"][0]["lowest_price"] == {
        "amount_minor": 1000,
        "currency": "USD",
        "basis": "base_listing_price",
        "excludes_shipping": True,
        "marketplaces": ["Flipkart"],
        "offers_with_unknown_shipping": 0,
        "out_of_stock": False,
    }


def test_verified_utc_history_is_used_for_current_price_but_snapshot_is_not(dbs, settings, client):
    db = dbs[DataMode.IMPORTED]
    run_import(db, settings, "snap.csv", csv_bytes([row("L-A", "Amazon")]))
    hist = [
        row("L-A", "Amazon", timestamp="2026-11-05T09:00:00Z", price="1300"),
        row("L-A", "Amazon", timestamp="2026-11-05T11:00:00Z", price="1250"),
    ]
    run_import(db, settings, "hist.csv", csv_bytes(hist), policy="require_utc")
    d = detail(client)
    o = d["offers"][0]
    assert o["price_minor"] == 125000
    assert o["current_observation"]["basis"] == "latest_verified_utc"
    assert o["current_observation"]["timestamp_quality"] == "utc"
    assert d["price_history"]["verified_observation_count"] == 2
    assert d["price_history"]["timezone_unknown_observation_count"] == 1
    assert listing(client)["items"][0]["lowest_price"]["amount_minor"] == 125000


def test_unordered_snapshots_give_no_current_price(dbs, settings, client):
    db = dbs[DataMode.IMPORTED]
    rows = [row("L-A", "Amazon"), row("L-A", "Amazon", timestamp="2026-11-04T12:00:00", price="1200")]
    run_import(db, settings, "a.csv", csv_bytes(rows))
    d = detail(client)
    o = d["offers"][0]
    assert o["current_observation"] is None and o["price_minor"] is None
    assert any(w["code"] == "ambiguous_unordered_snapshots" for w in o["warnings"])
    item = listing(client)["items"][0]
    assert item["lowest_price"] is None


def test_import_keeps_summaries_current_and_rebuild_is_idempotent(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    run_import(db, settings, "a.csv", csv_bytes([row("L-A", "Amazon"), row("L-B", "Myntra")]))
    assert db.product_summaries.count_documents({}) == 1
    first = db.product_summaries.find_one({}, {"built_at": 0})
    rebuild_product_summaries(db)
    assert db.product_summaries.find_one({}, {"built_at": 0}) == first
    assert dbs[DataMode.DEMO].product_summaries.count_documents({}) == 0
