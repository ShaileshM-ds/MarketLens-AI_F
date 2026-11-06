"""Phase 4 pricing edge cases through the real import + API path (throwaway databases)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from helpers import SAMPLE_ROW, csv_bytes
from marketlens_core.settings import DataMode
from test_importer_db import run_import

pytestmark = pytest.mark.integration


def row(listing, marketplace, **kw):
    return {**SAMPLE_ROW, "listing_id": listing, "marketplace": marketplace, "seller_id": f"S-{listing}", **kw}


@pytest.fixture
def client(settings, dbs):
    with TestClient(create_app(settings)) as c:
        yield c


def detail(client):
    return client.get("/api/v1/products/MCL0001", params={"mode": "imported"}).json()


def test_unknown_shipping_with_lower_base_makes_cheapest_uncertain(dbs, settings, client):
    rows = [row("L-A", "Amazon", price="1000", shipping_cost=""), row("L-B", "Flipkart", price="1100", shipping_cost="50")]
    run_import(dbs[DataMode.IMPORTED], settings, "a.csv", csv_bytes(rows))
    d = detail(client)
    a = next(o for o in d["offers"] if o["listing_id"] == "L-A")
    assert a["delivered_status"] == "cannot_be_confirmed" and a["delivered_price_minor"] is None
    cd = d["pricing"]["lowest_confirmed_delivered"]
    assert cd["amount_minor"] == 115000 and cd["certain_overall"] is False
    assert d["pricing"]["lowest_listed"]["listing_ids"] == ["L-A"]
    assert "shipping_unknown" in {q["code"] for q in d["quality_labels"]}
    item = client.get("/api/v1/products", params={"mode": "imported"}).json()["items"][0]
    assert item["lowest_delivered"] == {"amount_minor": 115000, "currency": "INR", "marketplaces": ["Flipkart"], "certain_overall": False}


def test_tied_delivered_prices_and_unavailable_cheapest(dbs, settings, client):
    rows = [
        row("L-A", "Amazon", price="1000", shipping_cost="100"),
        row("L-B", "Flipkart", price="1100", shipping_cost="0"),
        row("L-C", "Myntra", price="900", shipping_cost="0", availability="Out of Stock", stock_quantity="0"),
    ]
    run_import(dbs[DataMode.IMPORTED], settings, "a.csv", csv_bytes(rows))
    p = detail(client)["pricing"]
    assert p["lowest_confirmed_delivered"]["listing_ids"] == ["L-C"]
    av = p["lowest_confirmed_delivered_available"]
    assert av["amount_minor"] == 110000 and av["listing_ids"] == ["L-A", "L-B"]
    assert av["excluded"] == [{"listing_id": "L-C", "marketplace": "Myntra", "reason": "Reported out of stock"}]


def test_stale_summaries_are_rebuilt_once_and_only_the_read_model_changes(dbs, settings):
    from marketlens_core.explorer import SUMMARY_VERSION, ensure_summaries_current

    db = dbs[DataMode.IMPORTED]
    run_import(db, settings, "a.csv", csv_bytes([row("L-A", "Amazon")]))
    before = {c: list(db[c].find({}).sort("_id", 1)) for c in ("products", "offers", "observations", "reviews")}
    db.product_summaries.update_many({}, {"$set": {"summary_version": 1}, "$unset": {"offers.$[].delivered_minor": ""}})
    assert ensure_summaries_current(db) == 1
    assert db.product_summaries.find_one({})["summary_version"] == SUMMARY_VERSION
    assert db.product_summaries.find_one({})["offers"][0]["delivered_minor"] == 144000
    assert ensure_summaries_current(db) == 0  # already current: no writes
    assert {c: list(db[c].find({}).sort("_id", 1)) for c in before} == before
    assert ensure_summaries_current(dbs[DataMode.DEMO]) == 0


def test_missing_reference_and_advertised_discount(dbs, settings, client):
    run_import(dbs[DataMode.IMPORTED], settings, "a.csv", csv_bytes([row("L-A", "Amazon", original_price="", discount="")]))
    o = detail(client)["offers"][0]
    assert o["discount"]["status"] == "no_reference"
    assert o["discount"]["calculated_percent"] is None and o["discount"]["advertised_percent"] is None
