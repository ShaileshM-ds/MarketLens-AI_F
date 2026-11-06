"""History-file import: supplied review IDs, review dates, DATA_REQUIREMENTS report. Throwaway databases only."""

from pathlib import Path

import pytest

from conftest import p5_import, p5_row
from helpers import NOW, csv_bytes
from marketlens_core.importing import service
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration
WOMENS = Path(__file__).resolve().parents[1] / "data" / "samples" / "womens_clothing_all_in_one.csv"


def hrow(lid, day, price="1000", **kw):
    return p5_row(lid, "Amazon", price, "40", timestamp=f"2026-10-{day:02d}T09:00:00Z", review_id="R-1", review="Fine shirt.", rating="4", review_date="2026-09-01", reviewer_name="Sample reviewer", **kw)


def test_repeated_review_ids_create_one_review_with_its_date(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    done = p5_import(db, settings, [hrow("L-A", d) for d in range(1, 11)], NOW, policy="require_utc")
    assert done["summary"]["accepted"] == 10 and db.observations.count_documents({}) == 10
    assert db.reviews.count_documents({}) == 1
    r = db.reviews.find_one({})
    assert r["review_date"] == "2026-09-01" and r["reviewer_name"] == "Sample reviewer" and r["external_review_id"] == "R-1"
    again = p5_import(db, settings, [hrow("L-A", d) for d in range(1, 11)], NOW, policy="require_utc")
    assert again["summary"]["duplicate"] == 10 and db.reviews.count_documents({}) == 1


def test_invalid_review_date_is_quarantined(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    done = p5_import(db, settings, [hrow("L-A", 1) | {"review_date": "01/09/2026"}], NOW, policy="require_utc")
    assert done["summary"]["rejected_by_reason"] == {"invalid_timestamp": 1}


def test_history_check_report(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    rows = [hrow("L-A", d) for d in range(1, 11)] + [hrow("L-B", 3, availability="Out of Stock", stock_quantity="9")]
    run = service.create_run(db, filename="h.csv", data=csv_bytes(rows), user="t", settings=settings, now=NOW)
    cfg = {**run["suggested_config"], "timestamp_policy": "require_utc", "category_map": {"T-Shirts": "mens-clothing"}}
    ev = service.update_config(db, run["_id"], cfg, settings=settings, now=NOW)["evaluation"]
    checks = {c["id"]: c for c in ev["history_check"]["checks"]}
    assert set(checks) == {f"R{i}" for i in range(1, 10)}
    assert checks["R2"]["status"] == "fail" and "10" in checks["R2"]["detail"]  # 10 days < 180
    assert checks["R3"]["status"] == "pass"
    assert checks["R5"]["status"] == "pass"
    assert checks["R6"]["status"] == "fail"  # one contradiction quarantined
    assert checks["R9"]["status"] == "info"
    assert ev["history_check"]["ready"] is False
    # A snapshot-rule import gets no history report.
    snap = service.create_run(db, filename="s.csv", data=csv_bytes([p5_row("L-Z", "Amazon", "10", "1")]), user="t", settings=settings, now=NOW)
    assert service.update_config(db, snap["_id"], snap["suggested_config"], settings=settings, now=NOW)["evaluation"].get("history_check") is None


@pytest.mark.skipif(not WOMENS.exists(), reason="women's sample not present")
def test_womens_file_dry_run_in_a_throwaway_database(dbs, settings):
    db = dbs[DataMode.IMPORTED]
    run = service.create_run(db, filename=WOMENS.name, data=WOMENS.read_bytes(), user="t", settings=settings, now=NOW)
    fm = run["suggested_config"]["field_map"]
    assert fm["review_id"] == "review_id" and fm["review_date"] == "review_date" and fm["brand"] == "brand"
    cfg = {**run["suggested_config"], "timestamp_policy": "require_utc", "category_map": {"Women's Clothing": "womens-clothing"}}
    ev = service.update_config(db, run["_id"], cfg, settings=settings, now=NOW)["evaluation"]
    c = ev["counts"]
    # The file has 60 base_listing rows that share listing + UTC time with a price_history row but carry
    # different prices and fields. Both can't be true, so the later one is quarantined, never merged.
    assert c["rejected_by_reason"] == {"immutable_conflict": 60}
    assert c["accepted"] == 12715 - 60
    assert c["reviews_new"] == 61
    checks = {x["id"]: x["status"] for x in ev["history_check"]["checks"]}
    assert checks["R2"] == checks["R3"] == checks["R5"] == checks["R6"] == checks["R8"] == "pass"
    assert db.observations.count_documents({}) == 0  # preview only: nothing imported
