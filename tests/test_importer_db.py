"""Importer against a real MongoDB (skipped when unreachable)."""

import pytest

from helpers import NOW, SAMPLE_ROW, csv_bytes
from marketlens_core.db import MODE_COLLECTIONS
from marketlens_core.importing import service
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration


def run_import(db, settings, filename, data, *, policy=None, config_overrides=None):
    run = service.create_run(db, filename=filename, data=data, user="tester", settings=settings, now=NOW)
    cfg = dict(run["suggested_config"])
    if policy:
        cfg["timestamp_policy"] = policy
    if config_overrides:
        cfg.update(config_overrides)
    service.update_config(db, run["_id"], cfg, settings=settings, now=NOW)
    service.confirm_run(db, run["_id"], user="tester", now=NOW)
    done = service.process_next_job(db, settings=settings, now_fn=lambda: NOW)
    assert done is not None and done["status"] == "completed", done
    return done


def counts(db):
    return {c: db[c].count_documents({}) for c in ("products", "offers", "observations", "reviews")}


def test_collections_and_indexes_exist_in_every_mode(dbs):
    for db in dbs.values():
        names = set(db.list_collection_names())
        assert set(MODE_COLLECTIONS) <= names
        obs_idx = db.observations.index_information()
        assert "listing_observed_at" in obs_idx and "product_observed_at" in obs_idx
        assert "product_id_1" in db.offers.index_information()
        assert "run_row" in db.rejected_records.index_information()


def test_sample_import_counts_and_provenance(dbs, settings, sample_bytes):
    db = dbs[DataMode.IMPORTED]
    done = run_import(db, settings, "mens_clothing_dataset_enriched.csv", sample_bytes)
    s = done["summary"]
    assert (s["rows_total"], s["accepted"], s["duplicate"], s["rejected"]) == (1500, 1500, 0, 0)
    assert s["warning_rows"] == 44 and s["warning_count"] == 44
    assert s["warnings_by_type"] == {"stock_availability_contradiction": 44}
    assert s["created"] == {"products": 500, "offers": 1500, "observations": 1500, "reviews": 1500}
    assert counts(db) == {"products": 500, "offers": 1500, "observations": 1500, "reviews": 1500}

    # Seller IDs preserved, never merged by name.
    assert len(db.offers.distinct("seller_id")) == 1500
    assert len(db.offers.distinct("seller_name")) == 24
    # Timestamp decision.
    assert db.observations.count_documents({"timestamp_quality": "timezone_unknown", "observed_at": None}) == 1500
    # Categories and blanks.
    assert db.products.distinct("category") == ["mens-clothing"]
    assert len(db.products.distinct("source_category")) == 7
    assert db.products.count_documents({"brand": None, "size": None, "colour": None}) == 500
    # Provenance on every record.
    for coll in ("products", "offers", "observations", "reviews"):
        assert db[coll].count_documents({"synthetic": True, "provenance.ingestion_run_id": done["_id"]}) == db[coll].count_documents({})
    assert db.observations.count_documents({"raw": {"$exists": True}, "provenance.raw_source_ref": {"$regex": "#row="}}) == 1500
    # Contradictions kept and flagged.
    assert db.observations.count_documents({"flags": "stock_availability_contradiction", "availability": "Out of Stock"}) == 44
    assert db.rejected_records.count_documents({}) == 0
    # Original file retained.
    assert db.source_files.count_documents({}) == 1


def test_reimport_does_not_duplicate(dbs, settings, sample_bytes):
    db = dbs[DataMode.IMPORTED]
    first = run_import(db, settings, "mens.csv", sample_bytes)
    before = db.observations.find_one({"_id": "obs1|AMA-CLO-LIST-000001|source-time:2026-11-04T10:30:00"})
    second = run_import(db, settings, "mens.csv", sample_bytes)
    s = second["summary"]
    assert (s["accepted"], s["duplicate"], s["rejected"]) == (0, 1500, 0)
    assert s["created"] == {"products": 0, "offers": 0, "observations": 0, "reviews": 0}
    assert s["reviews_duplicate"] == 1500
    assert counts(db) == {"products": 500, "offers": 1500, "observations": 1500, "reviews": 1500}
    after = db.observations.find_one({"_id": before["_id"]})
    assert after == before and after["provenance"]["ingestion_run_id"] == first["_id"]


def test_duplicate_row_within_one_file(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    done = run_import(db, settings, "dup.csv", csv_bytes([SAMPLE_ROW, SAMPLE_ROW]))
    s = done["summary"]
    assert (s["accepted"], s["duplicate"]) == (1, 1)
    assert counts(db)["reviews"] == 1


def test_history_appends_new_immutable_observations(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    run_import(db, settings, "snapshot.csv", csv_bytes([SAMPLE_ROW]))
    snap_id = "obs1|AMA-CLO-LIST-000001|source-time:2026-11-04T10:30:00"
    snapshot_before = db.observations.find_one({"_id": snap_id})

    history = [
        {**SAMPLE_ROW, "timestamp": "2026-11-04T10:30:00Z", "price": "1350"},  # same clock time, now UTC
        {**SAMPLE_ROW, "timestamp": "2026-11-05T10:30:00Z", "price": "1300"},
    ]
    h = run_import(db, settings, "history.csv", csv_bytes(history), policy="require_utc")
    assert h["summary"]["accepted"] == 2
    obs = list(db.observations.find({"listing_id": "AMA-CLO-LIST-000001"}).sort("_id", 1))
    assert len(obs) == 3
    assert db.observations.find_one({"_id": snap_id}) == snapshot_before
    utc_obs = [o for o in obs if o["timestamp_quality"] == "utc"]
    assert all(o["history_eligible"] for o in utc_obs) and len(utc_obs) == 2

    again = run_import(db, settings, "history.csv", csv_bytes(history), policy="require_utc")
    assert (again["summary"]["accepted"], again["summary"]["duplicate"]) == (0, 2)


def test_history_policy_quarantines_timezone_unknown_rows(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    done = run_import(db, settings, "history.csv", csv_bytes([SAMPLE_ROW]), policy="require_utc")
    assert done["summary"]["rejected"] == 1
    rec = db.rejected_records.find_one({"run_id": done["_id"]})
    assert rec["reasons"][0]["code"] == "invalid_timestamp"
    assert "no timezone" in rec["reasons"][0]["message"]


def test_history_quarantines_stock_contradictions_but_snapshot_keeps_them(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    bad = {**SAMPLE_ROW, "availability": "Out of Stock", "stock_quantity": "25.0"}
    # Snapshot rule: kept with a warning.
    snap = run_import(db, settings, "snapshot.csv", csv_bytes([bad]))
    assert (snap["summary"]["accepted"], snap["summary"]["warning_rows"]) == (1, 1)
    # History rule: quarantined, original values kept, nothing stored.
    history = [
        {**bad, "timestamp": "2026-11-05T10:30:00Z"},
        {**SAMPLE_ROW, "timestamp": "2026-11-05T11:30:00Z"},
    ]
    h = run_import(db, settings, "history.csv", csv_bytes(history), policy="require_utc")
    s = h["summary"]
    assert (s["accepted"], s["rejected"], s["warning_rows"]) == (1, 1, 0)
    assert s["rejected_by_reason"] == {"stock_availability_contradiction": 1}
    rec = db.rejected_records.find_one({"run_id": h["_id"]})
    # Complete original row, unchanged.
    assert rec["row_number"] == 1
    assert rec["raw"] == {k: str(v) for k, v in history[0].items()}
    # Explicit reason.
    assert rec["reasons"][0]["code"] == "stock_availability_contradiction"
    assert "quarantined" in rec["reasons"][0]["message"]
    # Provenance.
    p = rec["provenance"]
    assert p["ingestion_run_id"] == h["_id"]
    assert p["source_filename"] == "history.csv" and p["source_file_id"]
    assert p["raw_source_ref"].endswith("history.csv#row=1")
    assert p["schema_version"] == "1" and p["timestamp_policy"] == "require_utc"
    assert p["quarantined_at"] is not None
    assert db.observations.count_documents({"timestamp_quality": "utc"}) == 1


def test_changed_values_for_stored_observation_are_rejected(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    run_import(db, settings, "a.csv", csv_bytes([SAMPLE_ROW]))
    done = run_import(db, settings, "b.csv", csv_bytes([{**SAMPLE_ROW, "price": "999"}]))
    assert done["summary"]["rejected"] == 1
    assert done["summary"]["rejected_by_reason"] == {"immutable_conflict": 1}
    assert db.observations.find_one({})["price_minor"] == 138000


def test_listing_cannot_be_relinked_to_another_product_or_seller(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    run_import(db, settings, "a.csv", csv_bytes([SAMPLE_ROW]))
    moved = {**SAMPLE_ROW, "timestamp": "2026-11-04T11:00:00", "product_id": "MCL9999"}
    done = run_import(db, settings, "b.csv", csv_bytes([moved]))
    assert done["summary"]["rejected_by_reason"] == {"listing_identity_conflict": 1}
    assert db.offers.find_one({"_id": "AMA-CLO-LIST-000001"})["product_id"] == "MCL0001"


def test_invalid_rows_quarantined_with_plain_reasons(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    rows = [
        SAMPLE_ROW,
        {**SAMPLE_ROW, "listing_id": "AMA-CLO-LIST-000002", "price": "12,00"},
        {**SAMPLE_ROW, "listing_id": ""},
    ]
    done = run_import(db, settings, "mixed.csv", csv_bytes(rows))
    s = done["summary"]
    assert (s["accepted"], s["rejected"]) == (1, 2)
    recs = list(db.rejected_records.find({"run_id": done["_id"]}).sort("row_number", 1))
    assert [r["row_number"] for r in recs] == [2, 3]
    assert "price '12,00'" in recs[0]["reasons"][0]["message"]
    assert recs[1]["reasons"][0]["message"] == "listing ID is blank"
    assert recs[0]["raw"]["price"] == "12,00"


def test_import_never_touches_demo_or_live(dbs, settings, sample_bytes):
    run_import(dbs[DataMode.IMPORTED], settings, "mens.csv", sample_bytes)
    for mode in (DataMode.DEMO, DataMode.LIVE):
        db = dbs[mode]
        assert {c: db[c].count_documents({}) for c in db.list_collection_names()} == {
            c: 0 for c in db.list_collection_names()
        }


def test_config_validation(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    run = service.create_run(db, filename="a.csv", data=csv_bytes([SAMPLE_ROW]), user="t", settings=settings, now=NOW)
    cfg = dict(run["suggested_config"])
    cfg["field_map"] = {**cfg["field_map"], "price": None}
    cfg["category_map"] = {"T-Shirts": "socks"}
    with pytest.raises(service.ServiceError) as exc:
        service.update_config(db, run["_id"], cfg, settings=settings, now=NOW)
    assert exc.value.status == 422
    text = " ".join(exc.value.problems)
    assert "Price" in text and "socks" in text


def test_confirm_requires_reviewed_mapping(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    run = service.create_run(db, filename="a.csv", data=csv_bytes([SAMPLE_ROW]), user="t", settings=settings, now=NOW)
    with pytest.raises(service.ServiceError) as exc:
        service.confirm_run(db, run["_id"], user="t", now=NOW)
    assert exc.value.status == 409
