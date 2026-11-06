"""Synthetic Demo generator (SCOPE §5): deterministic, Demo-only, synthetic, with a separate answer key."""

import hashlib
import json
from pathlib import Path

import pytest

from helpers import NOW
from marketlens_core.demo import generator
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration
REPO = Path(__file__).resolve().parents[1]


def fp(db):
    return {c: hashlib.sha256(json.dumps(list(db[c].find({}).sort("_id", 1)), default=str, sort_keys=True).encode()).hexdigest()
            for c in ("products", "offers", "observations", "reviews")}


@pytest.fixture
def generated(dbs, tmp_path):
    out = tmp_path / "export"
    summary = generator.generate_demo(dbs[DataMode.DEMO], export_dir=out, now=NOW)
    return summary, out


def test_generates_scope_ranges_all_synthetic_and_utc(dbs, generated):
    summary, _ = generated
    db = dbs[DataMode.DEMO]
    n = db.products.count_documents({})
    assert 30 <= n <= 50
    assert len(db.products.distinct("category")) >= 5
    assert summary["rejected"] == 0
    for c in ("products", "offers", "observations", "reviews"):
        assert db[c].count_documents({"synthetic": {"$ne": True}}) == 0, c
    assert db.observations.count_documents({"timestamp_quality": "utc", "history_eligible": True}) == db.observations.count_documents({})
    # 180+ distinct days for full-history products; brands are fictional and supplied, never parsed.
    days = db.observations.aggregate([{"$group": {"_id": "$product_id", "d": {"$addToSet": {"$dateToString": {"format": "%Y-%m-%d", "date": "$observed_at"}}}}}, {"$project": {"n": {"$size": "$d"}}}])
    counts = sorted(d["n"] for d in days)
    assert counts[-1] >= 180 and sum(1 for c in counts if c >= 180) >= 25
    assert db.products.count_documents({"brand": None}) == 0
    assert db.products.count_documents({"category": "mobile-phones", "storage": None}) == 0
    # Several sellers on some products, several observations per day for a few.
    multi_seller = db.offers.aggregate([{"$group": {"_id": {"p": "$product_id", "m": "$marketplace"}, "s": {"$addToSet": "$seller_id"}}}, {"$match": {"s.1": {"$exists": True}}}])
    assert len(list(multi_seller)) >= 2
    per_day = db.observations.aggregate([{"$group": {"_id": {"l": "$listing_id", "d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$observed_at"}}}, "n": {"$sum": 1}}}, {"$match": {"n": {"$gte": 3}}}, {"$limit": 1}])
    assert list(per_day)
    # Reviews: 3-15 per reviewed product, some products with none, plain labelled text.
    rc = {d["_id"]: d["n"] for d in db.reviews.aggregate([{"$group": {"_id": "$product_id", "n": {"$sum": 1}}}])}
    assert all(3 <= v <= 15 for v in rc.values()) and n - len(rc) >= 2
    assert db.reviews.count_documents({"review_source": {"$not": {"$regex": "Synthetic"}}}) == 0
    assert db.observations.count_documents({"flags": "stock_availability_contradiction"}) == 0


def test_answer_key_is_separate_and_covers_every_scenario(dbs, generated):
    summary, out = generated
    key = json.loads((out / "answer_key.json").read_text(encoding="utf-8"))
    types = {s["type"] for s in key["scenarios"]}
    assert types >= {"genuine_discount", "inflated_reference", "repeated_urgency", "shipping_offset", "seller_switch",
                     "market_wide_movement", "mixed_event_outcomes", "stable_prices", "sparse_missing_days", "insufficient_history"}
    db = dbs[DataMode.DEMO]
    for s in key["scenarios"]:
        for pid in s["product_ids"]:
            assert db.products.find_one({"_id": pid}), (s["type"], pid)
    assert key["seed"] == generator.DEFAULT_SEED
    assert (out / "demo_dataset.csv").exists()
    # The key lives only in the export file: never in any database collection.
    for c in db.list_collection_names():
        assert not db[c].find_one({"scenarios": {"$exists": True}}), c
    # Analytics/service code never reads the answer key.
    offenders = [p for p in (REPO / "shared" / "marketlens_core").rglob("*.py") if "answer_key" in p.read_text(encoding="utf-8") and "demo" not in p.parts]
    assert offenders == []


def test_same_seed_is_byte_identical(dbs, tmp_path, mongo_client, settings):
    a, b = tmp_path / "a", tmp_path / "b"
    generator.generate_demo(dbs[DataMode.DEMO], export_dir=a, now=NOW)
    other = mongo_client[settings.mongo_db_demo + "_twin"]
    try:
        generator.generate_demo(other, export_dir=b, now=NOW)
        for f in ("demo_dataset.csv", "answer_key.json"):
            assert (a / f).read_bytes() == (b / f).read_bytes(), f
        assert sorted(o["content_hash"] for o in dbs[DataMode.DEMO].observations.find({}, {"content_hash": 1})) == sorted(
            o["content_hash"] for o in other.observations.find({}, {"content_hash": 1}))
    finally:
        mongo_client.drop_database(other.name)


def test_demo_only_refuses_second_run_and_reset_clears_only_demo(dbs, settings, mongo_client, tmp_path):
    from conftest import p5_import, p5_row

    imported = dbs[DataMode.IMPORTED]
    p5_import(imported, settings, [p5_row("L-A", "Amazon", "1380", "60")], NOW)
    mongo_client[settings.mongo_db_accounts].users.insert_one({"_id": "keep", "username": "keep", "role": "consumer"})
    before = {m: fp(dbs[m]) for m in (DataMode.IMPORTED, DataMode.LIVE)}
    demo = dbs[DataMode.DEMO]
    generator.generate_demo(demo, export_dir=tmp_path / "x", now=NOW)
    with pytest.raises(generator.DemoError):
        generator.generate_demo(demo, export_dir=tmp_path / "y", now=NOW)
    demo.watchlist_items.insert_one({"user_id": "keep", "product_id": "DEMO-P-001"})
    removed = generator.reset_demo(demo)
    assert removed["observations"] > 0
    assert all(demo[c].count_documents({}) == 0 for c in demo.list_collection_names())
    assert {m: fp(dbs[m]) for m in (DataMode.IMPORTED, DataMode.LIVE)} == before
    assert mongo_client[settings.mongo_db_accounts].users.count_documents({"_id": "keep"}) == 1
    with pytest.raises(generator.DemoError):
        generator.reset_demo(imported)  # refuses anything that isn't a demo database


def test_admin_api_queues_jobs_and_is_admin_only(p5, mongo_client):
    from app.auth import hash_password

    mongo_client[p5.settings.mongo_db_accounts].users.insert_one({"_id": "adm", "username": "adm", "role": "admin", "password_hash": hash_password("adm-test-password-1")})
    assert p5.alice.post("/api/v1/admin/demo/generate").status_code == 403
    assert p5.anon.get("/api/v1/admin/demo/status").status_code == 401
    p5.bob.post("/api/v1/auth/logout")
    assert p5.bob.post("/api/v1/auth/login", json={"username": "adm", "password": "adm-test-password-1"}).status_code == 200
    st = p5.bob.get("/api/v1/admin/demo/status").json()
    assert st["products"] == 0 and st["database"] == p5.settings.mongo_db_demo
    assert p5.bob.post("/api/v1/admin/demo/generate").json()["status"] == "queued"
    assert p5.bob.post("/api/v1/admin/demo/reset", json={"confirm": "wrong"}).status_code == 422
    assert p5.bob.post("/api/v1/admin/demo/reset", json={"confirm": "RESET DEMO"}).json()["status"] == "queued"
    demo = p5.dbs[DataMode.DEMO]
    assert {j["type"] for j in demo.jobs.find({})} == {"demo_generate", "demo_reset"}
    assert p5.db.jobs.count_documents({"type": {"$in": ["demo_generate", "demo_reset"]}}) == 0
