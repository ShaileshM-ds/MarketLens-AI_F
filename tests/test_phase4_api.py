"""Phase 4 API: price intelligence on product details, explorer sorts/filters, multi-product comparison.

Expected values are computed from the stored observations, never hard-coded.
"""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal

import pytest

from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration


def get(env, path, **params):
    params.setdefault("mode", "imported")
    return env["client"].get(path, params=params)


def fingerprint(db):
    out = {}
    for c in ("products", "offers", "observations", "reviews"):
        h = hashlib.sha256()
        for d in db[c].find({}).sort("_id", 1):
            h.update(json.dumps(d, sort_keys=True, default=str).encode())
        out[c] = (db[c].count_documents({}), h.hexdigest())
    return out


@pytest.fixture(scope="module")
def env(sample_env):
    sample_env["before"] = {m: fingerprint(sample_env["mongo"][sample_env["settings"].database_for(m)]) for m in DataMode}
    return sample_env


def stored(env, pid):
    return {o["listing_id"]: o for o in env["db"].observations.find({"product_id": pid})}


def pct(price, ref):
    return float(((Decimal(ref - price) / Decimal(ref)) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------- product details ----------
def test_detail_delivered_prices_and_three_designations_match_stored_values(env):
    d = get(env, "/api/v1/products/MCL0001").json()
    obs = stored(env, "MCL0001")
    for o in d["offers"]:
        s = obs[o["listing_id"]]
        assert o["delivered_price_minor"] == s["price_minor"] + s["shipping_minor"]
        assert o["delivered_status"] == "confirmed"
    delivered = {lid: s["price_minor"] + s["shipping_minor"] for lid, s in obs.items()}
    p = d["pricing"]
    assert p["currency"] == "INR"
    assert p["lowest_listed"]["amount_minor"] == min(s["price_minor"] for s in obs.values())
    assert p["lowest_confirmed_delivered"]["amount_minor"] == min(delivered.values())
    assert p["lowest_confirmed_delivered"]["certain_overall"] is True
    avail = [lid for lid, s in obs.items() if s["availability"] in ("In Stock", "Limited Stock") and not s["flags"]]
    assert p["lowest_confirmed_delivered_available"]["amount_minor"] == min(delivered[l] for l in avail)


def test_detail_discount_analysis_per_offer(env):
    d = get(env, "/api/v1/products/MCL0001").json()
    obs = stored(env, "MCL0001")
    for o in d["offers"]:
        s = obs[o["listing_id"]]
        a = o["discount"]
        assert a["reference_price_minor"] == s["reference_price_minor"] and a["price_minor"] == s["price_minor"]
        assert a["calculated_percent"] == pct(s["price_minor"], s["reference_price_minor"])
        assert a["advertised_percent"] == s["advertised_discount_percent"]
        assert a["status"] in ("consistent", "differs")
        assert o["coupon_discount_minor"] == s["coupon_discount_minor"]  # shown, not subtracted
        assert o["delivered_price_minor"] == s["price_minor"] + s["shipping_minor"]


def test_detail_availability_quality_labels_and_history(env):
    flagged = env["db"].observations.find_one({"flags": "stock_availability_contradiction"})
    d = get(env, f"/api/v1/products/{flagged['product_id']}").json()
    summary = d["availability_summary"]
    assert summary["contradictions"] >= 1
    assert sum(summary[k] for k in ("in_stock", "limited_stock", "out_of_stock", "unknown")) == len(d["offers"])
    codes = {q["code"] for q in d["quality_labels"]}
    assert {"synthetic_dataset", "timezone_unknown", "availability_contradiction", "missing_product_metadata"} <= codes
    assert "verified_history" not in codes and "shipping_unknown" not in codes
    o = next(o for o in d["offers"] if o["listing_id"] == flagged["listing_id"])
    assert o["listing_id"] not in d["pricing"]["lowest_confirmed_delivered_available"]["listing_ids"]
    assert d["price_history"]["reason"] == (
        "Verified historical price data is not available for this product yet. "
        "Current comparisons use imported snapshot observations."
    )
    assert d["price_history"]["status"] == "unavailable" and "points" not in d["price_history"]


# ---------- explorer extensions ----------
def _pages(env, **params):
    items, page = [], 1
    while True:
        r = get(env, "/api/v1/products", page=page, page_size=60, **params).json()
        items += r["items"]
        if page * 60 >= r["total"]:
            return items
        page += 1


def _per_product(env):
    out = {}
    for s in env["db"].observations.find({}):
        out.setdefault(s["product_id"], []).append(s)
    return out


def test_explorer_items_carry_confirmed_delivered_and_available_counts(env):
    item = get(env, "/api/v1/products", q="MCL0001").json()["items"][0]
    obs = list(stored(env, "MCL0001").values())
    assert item["lowest_delivered"]["amount_minor"] == min(s["price_minor"] + s["shipping_minor"] for s in obs)
    assert item["lowest_delivered"]["certain_overall"] is True
    assert item["available_offer_count"] == sum(1 for s in obs if s["availability"] in ("In Stock", "Limited Stock") and not s["flags"])
    assert item["max_advertised_discount"] == max(s["advertised_discount_percent"] for s in obs)


def test_sort_by_confirmed_delivered_price(env):
    per = _per_product(env)
    items = _pages(env, sort="delivered_asc")
    vals = [i["lowest_delivered"]["amount_minor"] for i in items]
    assert vals == sorted(vals)
    assert {i["product_id"]: i["lowest_delivered"]["amount_minor"] for i in items} == {
        pid: min(s["price_minor"] + s["shipping_minor"] for s in obs) for pid, obs in per.items()
    }
    desc = [i["lowest_delivered"]["amount_minor"] for i in _pages(env, sort="delivered_desc")]
    assert desc == sorted(desc, reverse=True)


def test_sort_by_discount_and_available_offers(env):
    items = _pages(env, sort="discount_desc")
    vals = [i["max_advertised_discount"] for i in items]
    assert vals == sorted(vals, reverse=True)
    items = _pages(env, sort="available_desc")
    counts = [i["available_offer_count"] for i in items]
    assert counts == sorted(counts, reverse=True)
    for a, b in zip(items, items[1:]):
        if a["available_offer_count"] == b["available_offer_count"]:
            assert (a["name"].lower(), a["product_id"]) <= (b["name"].lower(), b["product_id"])


def test_discount_range_and_known_delivered_filters(env):
    ids = {i["product_id"] for i in _pages(env, discount_min=30, discount_max=40)}
    expected = set(env["db"].observations.distinct("product_id", {"advertised_discount_percent": {"$gte": 30, "$lte": 40}}))
    assert ids == expected
    known = _pages(env, delivered_known="true")
    assert len(known) == len(set(env["db"].observations.distinct("product_id", {"shipping_known": True})))
    assert get(env, "/api/v1/products", discount_min=50, discount_max=10).status_code == 422
    assert get(env, "/api/v1/products", discount_min=101).status_code == 422
    assert get(env, "/api/v1/products", sort="cheapest").status_code == 422


# ---------- multi-product comparison ----------
def test_compare_returns_products_in_requested_order_with_consistent_pricing(env):
    r = get(env, "/api/v1/compare", ids=["MCL0002", "MCL0001"])
    assert r.status_code == 200
    body = r.json()
    assert [p["product_id"] for p in body["products"]] == ["MCL0002", "MCL0001"]
    assert body["missing"] == []
    for p in body["products"]:
        d = get(env, f"/api/v1/products/{p['product_id']}").json()
        assert p["pricing"] == d["pricing"]
        assert p["offer_count"] == len(d["offers"])
        assert p["available_offer_count"] == sum(1 for o in d["offers"] if o["purchasable"])
        assert p["availability_summary"] == d["availability_summary"]
        assert p["marketplaces"] == sorted({o["marketplace"] for o in d["offers"]})
        refs = [o["reference_price_minor"] for o in d["offers"]]
        assert p["reference_price_range"] == {"min": min(refs), "max": max(refs), "currency": "INR"}
        assert p["reviews_summary"]["count"] == d["reviews_summary"]["count"]
        assert {q["code"] for q in p["quality_labels"]} == {q["code"] for q in d["quality_labels"]}
        assert "_id" not in p and "offers" not in p


def test_compare_comparability_warnings(env):
    cats = {p["_id"]: p["source_category"] for p in env["db"].products.find({}, {"source_category": 1})}
    a = "MCL0001"
    b = next(pid for pid, c in cats.items() if c != cats[a])
    body = get(env, "/api/v1/compare", ids=[a, b]).json()
    assert any("sub-categor" in w.lower() for w in body["comparability_warnings"])
    same = next(pid for pid, c in sorted(cats.items()) if c == cats[a] and pid != a)
    assert get(env, "/api/v1/compare", ids=[a, same]).json()["comparability_warnings"] == []


def test_compare_validation_and_isolation(env):
    assert get(env, "/api/v1/compare", ids=["MCL0001", "MCL0002", "MCL0003", "MCL0004", "MCL0005"]).status_code == 422
    assert get(env, "/api/v1/compare").status_code == 422
    assert get(env, "/api/v1/compare", ids=["x" * 200]).status_code == 422
    assert get(env, "/api/v1/compare", ids=[""]).status_code == 422
    dup = get(env, "/api/v1/compare", ids=["MCL0001", "MCL0001"]).json()
    assert [p["product_id"] for p in dup["products"]] == ["MCL0001"]
    miss = get(env, "/api/v1/compare", ids=["MCL0001", "NOPE"]).json()
    assert [p["product_id"] for p in miss["products"]] == ["MCL0001"] and miss["missing"] == ["NOPE"]
    demo = get(env, "/api/v1/compare", ids=["MCL0001"], mode="demo").json()
    assert demo["products"] == [] and demo["missing"] == ["MCL0001"]
    assert get(env, "/api/v1/compare", ids=["MCL0001"], mode="live").status_code == 409


# ---------- integrity (keep last) ----------
def test_phase4_requests_change_nothing_and_flags_survive(env):
    for m in DataMode:
        assert fingerprint(env["mongo"][env["settings"].database_for(m)]) == env["before"][m]
    db = env["db"]
    assert db.observations.count_documents({"flags": "stock_availability_contradiction"}) == 44
    assert db.observations.count_documents({"observed_at": {"$ne": None}}) == 0  # no fabricated UTC times
    assert db.observations.count_documents({}) == 1500
    offers = {o["_id"]: o["product_id"] for o in db.offers.find({}, {"product_id": 1})}
    assert all(offers[r["listing_id"]] == r["product_id"] for r in db.reviews.find({}, {"listing_id": 1, "product_id": 1}))
