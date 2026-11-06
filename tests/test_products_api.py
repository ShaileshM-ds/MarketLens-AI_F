"""Product Explorer API against a real MongoDB loaded with the sample dataset.

The sample is imported once per module into throwaway `mltest_*` databases
(never the real ones). Every request here is read-only; the last test checks it.
"""

import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.main import create_app
from conftest import MONGO_URI
from helpers import NOW, SAMPLE_PATH
from marketlens_core.db import ensure_mode_indexes
from marketlens_core.importing import service
from marketlens_core.settings import DataMode, Settings

pytestmark = pytest.mark.integration
API = "/api/v1/products"


def _fingerprint(db) -> dict:
    out = {}
    for c in ("products", "offers", "observations", "reviews"):
        h = hashlib.sha256()
        for d in db[c].find({}).sort("_id", 1):
            h.update(json.dumps(d, sort_keys=True, default=str).encode())
        out[c] = (db[c].count_documents({}), h.hexdigest())
    return out


@pytest.fixture(scope="module")
def env(mongo_client):
    if not SAMPLE_PATH.exists():
        pytest.skip("sample dataset missing")
    prefix = f"mltest_{uuid.uuid4().hex[:10]}"
    s = Settings(
        mongo_uri=MONGO_URI,
        mongo_db_demo=f"{prefix}_demo",
        mongo_db_imported=f"{prefix}_imported",
        mongo_db_live=f"{prefix}_live",
        mongo_db_accounts=f"{prefix}_accounts",
    )
    for m in DataMode:
        ensure_mode_indexes(mongo_client[s.database_for(m)])
    db = mongo_client[s.mongo_db_imported]
    run = service.create_run(db, filename="mens.csv", data=SAMPLE_PATH.read_bytes(), user="t", settings=s, now=NOW)
    service.update_config(db, run["_id"], run["suggested_config"], settings=s, now=NOW)
    service.confirm_run(db, run["_id"], user="t", now=NOW)
    service.process_next_job(db, settings=s, now_fn=lambda: NOW)
    before = {m: _fingerprint(mongo_client[s.database_for(m)]) for m in DataMode}
    with TestClient(create_app(s)) as client:
        yield {"client": client, "db": db, "settings": s, "before": before, "mongo": mongo_client}
    for name in (s.mongo_db_demo, s.mongo_db_imported, s.mongo_db_live, s.mongo_db_accounts):
        mongo_client.drop_database(name)


def get(env, path=API, **params):
    params.setdefault("mode", "imported")
    return env["client"].get(path, params=params)


def all_ids(env, **params):
    ids, page = [], 1
    while True:
        r = get(env, page=page, page_size=60, **params).json()
        ids += [i["product_id"] for i in r["items"]]
        if page * 60 >= r["total"]:
            return ids, r["total"]
        page += 1


def products_with_offer(env, match: dict) -> set:
    return set(env["db"].observations.distinct("product_id", match))


# ---------- listing and workspaces ----------
def test_lists_imported_products(env):
    r = get(env)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "imported" and body["total"] == 500
    assert body["page"] == 1 and body["page_size"] == 24 and len(body["items"]) == 24
    item = body["items"][0]
    for key in ("product_id", "name", "category", "category_label", "offer_count", "matching_offer_count", "lowest_price", "availability", "synthetic", "source_label"):
        assert key in item
    assert item["category"] == "mens-clothing" and item["category_label"] == "Men's clothing"
    assert item["synthetic"] is True
    assert item["brand"] is None and item["size"] is None and item["colour"] is None
    lp = item["lowest_price"]
    assert isinstance(lp["amount_minor"], int) and lp["currency"] == "INR"
    assert lp["basis"] == "base_listing_price" and lp["excludes_shipping"] is True
    assert "_id" not in item and "offers" not in item


def test_demo_is_empty_and_live_is_unavailable(env):
    r = get(env, mode="demo").json()
    assert r["total"] == 0 and r["items"] == []
    live = get(env, mode="live")
    assert live.status_code == 409 and "Live" in live.json()["detail"]
    assert get(env, mode="nope").status_code == 422


# ---------- search ----------
def test_search_exact_product_id_any_case(env):
    for q in ("MCL0001", "mcl0001"):
        r = get(env, q=q).json()
        assert r["total"] == 1 and r["items"][0]["product_id"] == "MCL0001"


def test_search_partial_name_case_insensitive(env):
    a = get(env, q="crew-neck").json()
    b = get(env, q="CREW-NECK").json()
    assert a["total"] == b["total"] > 0
    assert all("crew-neck" in i["name"].lower() for i in a["items"])


def test_search_no_results_and_special_characters_are_literal(env):
    assert get(env, q="zzzz-no-such-thing").json()["total"] == 0
    assert get(env, q=".*").json()["total"] == 0  # not a regex wildcard
    names = [p["name"].lower() for p in env["db"].products.find({}, {"name": 1})]
    for q in ("(", "(style 001)", "[a-", "\\", "$where", '{"$gt": ""}'):
        r = get(env, q=q)
        # Treated as literal text: matches exactly the names that contain it (every name has "(Style NNN)").
        assert r.status_code == 200 and r.json()["total"] == sum(q.lower() in n for n in names), q
    assert get(env, q="x" * 101).status_code == 422


# ---------- filters ----------
def test_category_filter(env):
    assert get(env, category="mens-clothing").json()["total"] == 500
    assert get(env, category="womens-clothing").json()["total"] == 0
    assert get(env, category="socks").status_code == 422


def test_marketplace_filter_restricts_offers(env):
    r = get(env, marketplace="Amazon", q="MCL0001").json()
    item = r["items"][0]
    assert item["matching_offer_count"] == 1 and item["matching_marketplaces"] == ["Amazon"]
    assert item["lowest_price"]["amount_minor"] == 138000  # Amazon's price, not Flipkart's lower one
    assert get(env, marketplace="Amazon").json()["total"] == 500
    two = get(env, marketplace=["Amazon", "Myntra"], q="MCL0001").json()["items"][0]
    assert two["matching_marketplaces"] == ["Amazon", "Myntra"]
    assert get(env, marketplace="Etsy").json()["total"] == 0


def test_price_range_on_base_price(env):
    r = get(env, currency="INR", price_min_minor=137000, price_max_minor=137000, q="MCL0001").json()
    item = r["items"][0]
    assert item["lowest_price"]["amount_minor"] == 137000
    assert item["matching_marketplaces"] == ["Flipkart"]
    ids, total = all_ids(env, currency="INR", price_min_minor=100000, price_max_minor=150000)
    assert set(ids) == products_with_offer(env, {"price_minor": {"$gte": 100000, "$lte": 150000}})


def test_price_range_validation(env):
    bad = get(env, currency="INR", price_min_minor=200000, price_max_minor=100000)
    assert bad.status_code == 422 and "minimum" in bad.json()["detail"].lower()
    assert get(env, price_min_minor=100).status_code == 422  # currency required with prices
    assert get(env, currency="INR", price_min_minor=-1).status_code == 422


def test_availability_filter(env):
    ids, _ = all_ids(env, availability="out_of_stock")
    assert set(ids) == products_with_offer(env, {"availability": "Out of Stock"})
    assert get(env, availability="sold_out").status_code == 422


def test_rating_filters(env):
    ids, _ = all_ids(env, seller_rating_min=4.5)
    assert set(ids) == products_with_offer(env, {"seller_rating": {"$gte": 4.5}})
    ids, _ = all_ids(env, product_rating_min=4.5)
    assert set(ids) == products_with_offer(env, {"product_rating": {"$gte": 4.5}})
    assert get(env, product_rating_min=6).status_code == 422


def test_free_shipping_filter(env):
    ids, _ = all_ids(env, free_shipping="true")
    assert set(ids) == products_with_offer(env, {"shipping_known": True, "shipping_minor": 0})


def test_combined_filters_apply_to_the_same_offer(env):
    ids, _ = all_ids(env, marketplace="Myntra", free_shipping="true", availability="in_stock")
    expected = products_with_offer(
        env, {"marketplace": "Myntra", "shipping_minor": 0, "shipping_known": True, "availability": "In Stock"}
    )
    assert set(ids) == expected


# ---------- sorting ----------
def _expected_names(env):
    return sorted(((p["name"].lower(), p["_id"]) for p in env["db"].products.find({}, {"name": 1})))


def test_sort_by_name(env):
    asc, _ = all_ids(env, sort="name_asc")
    assert asc == [pid for _, pid in _expected_names(env)]
    desc, _ = all_ids(env, sort="name_desc")
    names = {p["_id"]: p["name"].lower() for p in env["db"].products.find({}, {"name": 1})}
    assert [names[i] for i in desc] == sorted((names[i] for i in desc), reverse=True)


def _pages(env, **params):
    items, page = [], 1
    while True:
        r = get(env, page=page, page_size=60, **params).json()
        items += r["items"]
        if page * 60 >= r["total"]:
            return items
        page += 1


def test_sort_by_price_with_stable_ties(env):
    items = _pages(env, sort="price_asc")
    keys = [(i["lowest_price"]["amount_minor"], i["name"].lower(), i["product_id"]) for i in items]
    assert keys == sorted(keys)
    items = _pages(env, sort="price_desc")
    prices = [i["lowest_price"]["amount_minor"] for i in items]
    assert prices == sorted(prices, reverse=True)
    for a, b in zip(items, items[1:]):
        if a["lowest_price"]["amount_minor"] == b["lowest_price"]["amount_minor"]:
            assert (a["name"].lower(), a["product_id"]) <= (b["name"].lower(), b["product_id"])


def test_sort_by_rating_and_offer_count(env):
    items = _pages(env, sort="rating_desc")
    ratings = [i["product_rating"]["max"] for i in items]
    assert ratings == sorted(ratings, reverse=True)
    items = _pages(env, sort="offers_desc")
    assert all(i["matching_offer_count"] == 3 for i in items)
    assert [i["product_id"] for i in items] == [pid for _, pid in _expected_names(env)]  # tie -> name
    assert get(env, sort="popularity").status_code == 422


# ---------- pagination ----------
def test_pagination(env):
    p1 = get(env, page=1, page_size=10).json()
    p2 = get(env, page=2, page_size=10).json()
    ids1 = [i["product_id"] for i in p1["items"]]
    ids2 = [i["product_id"] for i in p2["items"]]
    assert len(ids1) == len(ids2) == 10 and not set(ids1) & set(ids2)
    assert [i["product_id"] for i in get(env, page=1, page_size=10).json()["items"]] == ids1  # stable
    ids, total = all_ids(env)
    assert total == 500 and len(ids) == len(set(ids)) == 500
    beyond = get(env, page=99, page_size=60).json()
    assert beyond["items"] == [] and beyond["total"] == 500
    assert get(env, page=0).status_code == 422
    assert get(env, page_size=61).status_code == 422
    assert get(env, page="abc").status_code == 422


# ---------- details ----------
def test_product_detail_offers_and_prices(env):
    r = get(env, f"{API}/MCL0001")
    assert r.status_code == 200
    d = r.json()
    assert d["product"]["product_id"] == "MCL0001" and d["product"]["synthetic"] is True
    offers = {o["marketplace"]: o for o in d["offers"]}
    assert set(offers) == {"Amazon", "Flipkart", "Myntra"}
    expected = {o["marketplace"]: o for o in env["db"].offers.find({"product_id": "MCL0001"})}
    for m, o in offers.items():
        assert o["listing_id"] == expected[m]["_id"] and o["seller_id"] == expected[m]["seller_id"]
    assert (offers["Amazon"]["price_minor"], offers["Amazon"]["shipping_minor"], offers["Amazon"]["total_minor"]) == (138000, 6000, 144000)
    assert (offers["Flipkart"]["price_minor"], offers["Flipkart"]["total_minor"]) == (137000, 143000)
    assert (offers["Myntra"]["price_minor"], offers["Myntra"]["shipping_minor"], offers["Myntra"]["total_minor"]) == (148000, 0, 148000)
    assert offers["Myntra"]["free_shipping"] is True
    assert offers["Flipkart"]["is_lowest_base"] and offers["Flipkart"]["is_lowest_delivered"]
    assert not offers["Myntra"]["is_lowest_base"]
    cmp = d["comparison"]
    assert cmp["lowest_base_price_minor"] == 137000 and cmp["lowest_delivered_price_minor"] == 143000
    o = offers["Amazon"]
    assert o["current_observation"]["source_timestamp"] == "2026-11-04T10:30:00"
    assert o["current_observation"]["timestamp_quality"] == "timezone_unknown"
    assert o["current_observation"]["basis"] == "single_snapshot_timezone_unknown"
    assert o["product_url"] is None


def test_product_detail_history_unavailable_and_reviews_summary(env):
    d = get(env, f"{API}/MCL0001").json()
    h = d["price_history"]
    assert h["status"] == "unavailable"
    assert h["verified_observation_count"] == 0 and h["timezone_unknown_observation_count"] == 3
    assert "snapshot" in h["reason"].lower()
    assert "points" not in h
    rs = d["reviews_summary"]
    ratings = [r["review_rating"] for r in env["db"].reviews.find({"product_id": "MCL0001"})]
    assert rs["count"] == 3 and rs["rated_count"] == 3
    assert rs["average_review_rating"] == round(sum(ratings) / 3, 2)
    assert "mean" in rs["formula"].lower()
    assert d["provenance"]["synthetic"] is True


def test_product_detail_contradiction_flagged_and_excluded(env):
    flagged = env["db"].observations.find_one({"flags": "stock_availability_contradiction"})
    d = get(env, f"{API}/{flagged['product_id']}").json()
    o = next(o for o in d["offers"] if o["listing_id"] == flagged["listing_id"])
    assert o["stock_quantity"] == flagged["stock_quantity"] and o["availability"] == flagged["availability"]
    assert any(w["message"] == "Availability and reported stock quantity disagree." for w in o["warnings"])
    assert o["purchasable"] is False and o["is_lowest_base"] is False
    assert any(x["listing_id"] == flagged["listing_id"] for x in d["comparison"]["excluded"])


def test_product_detail_missing_and_cross_workspace(env):
    assert get(env, f"{API}/MCL9999").status_code == 404
    assert get(env, f"{API}/MCL0001", mode="demo").status_code == 404
    assert get(env, f"{API}/MCL0001", mode="live").status_code == 409
    assert get(env, f"{API}/" + "x" * 200).status_code == 422


def test_reviews_endpoint(env):
    r = get(env, f"{API}/MCL0001/reviews").json()
    assert r["total"] == 3 and len(r["items"]) == 3
    by_listing = {o["_id"]: o["marketplace"] for o in env["db"].offers.find({"product_id": "MCL0001"})}
    for rev in r["items"]:
        assert rev["marketplace"] == by_listing[rev["listing_id"]]
        assert rev["review_rating"] in (3, 4, 5) and rev["text"]
        assert rev["synthetic"] is True and "_id" not in rev
    assert get(env, f"{API}/MCL0001/reviews", page_size=101).status_code == 422
    assert get(env, f"{API}/MCL9999/reviews").status_code == 404
    assert get(env, f"{API}/MCL0001/reviews", mode="demo").status_code == 404


# ---------- filter metadata ----------
def test_filter_metadata(env):
    f = get(env, f"{API}/filters").json()
    assert f["total_products"] == 500
    assert f["categories"] == [{"slug": "mens-clothing", "label": "Men's clothing", "count": 500}]
    assert {m["name"]: m["count"] for m in f["marketplaces"]} == {"Amazon": 500, "Flipkart": 500, "Myntra": 500}
    assert f["currencies"] == [{"code": "INR", "min_price_minor": 51000, "max_price_minor": 536000}]
    assert {a["value"] for a in f["availability"]} == {"in_stock", "limited_stock", "out_of_stock"}
    assert f["conditions"] == ["New"]
    assert f["brands"] == [] and f["sizes"] == [] and f["colours"] == []
    assert f["catalog_status"] == {"products": 500, "summarized": 500, "up_to_date": True}
    assert f["data_basis"]["verified_history"] is False and f["data_basis"]["all_synthetic"] is True
    demo = get(env, f"{API}/filters", mode="demo").json()
    assert demo["total_products"] == 0 and demo["marketplaces"] == []


# ---------- integrity (keep last) ----------
def test_requests_did_not_modify_any_data(env):
    for m in DataMode:
        assert _fingerprint(env["mongo"][env["settings"].database_for(m)]) == env["before"][m]
    assert env["before"][DataMode.DEMO]["products"][0] == 0
    assert env["before"][DataMode.LIVE]["observations"][0] == 0
