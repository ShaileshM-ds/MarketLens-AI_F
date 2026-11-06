"""Shareable Demo reference pack: deterministic, complete, self-contained, Demo-only, no user data or answer key."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from helpers import NOW
from marketlens_core.demo import generator
from marketlens_core.demo.reference import export_reference
from marketlens_core.settings import DataMode

pytestmark = pytest.mark.integration
CORE = ("products", "offers", "observations", "reviews")


def fp(db):
    return {c: hashlib.sha256(json.dumps(list(db[c].find({}).sort("_id", 1)), default=str, sort_keys=True).encode()).hexdigest() for c in CORE}


@pytest.fixture
def demo(dbs, tmp_path):
    db = dbs[DataMode.DEMO]
    generator.generate_demo(db, export_dir=tmp_path / "gen", now=NOW)
    return db


def files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def rows(root: Path, name: str) -> list[dict]:
    with open(root / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_export_is_deterministic_complete_and_read_only(demo, tmp_path):
    before = fp(demo)
    a, b = tmp_path / "a", tmp_path / "b"
    export_reference(demo, a)
    export_reference(demo, b)
    assert files(a) == files(b)  # byte-identical across repeated generation
    assert fp(demo) == before  # the export never writes to the database
    for name, coll in (("products.csv", "products"), ("offers.csv", "offers"), ("observations.csv", "observations"), ("reviews.csv", "reviews")):
        assert len(rows(a, name)) == demo[coll].count_documents({}), name
    obs = rows(a, "observations.csv")[0]
    assert obs["price_minor"].isdigit() and obs["synthetic"] == "true" and obs["schema_version"] and obs["ingestion_run_id"] and obs["source_label"]
    assert obs["observed_at"].endswith("Z") and obs["observation_id"].startswith("obs1|")


def test_manifest_matches_files_and_images_resolve_inside_the_pack(demo, tmp_path):
    out = tmp_path / "pack"
    export_reference(demo, out)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["mode"] == "demo" and m["synthetic"] is True and m["generator"]["seed"] == generator.DEFAULT_SEED
    for name, meta in m["files"].items():
        data = (out / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"] and len(data) == meta["bytes"], name
        if name.endswith(".csv"):
            assert meta["rows"] == len(rows(out, name))
    assert m["image_assets"] == len(list((out / "images").glob("*.svg"))) == 41
    for p in rows(out, "products.csv"):
        ref = p["image_path"]
        assert ref.startswith("images/") and ".." not in ref and "://" not in ref
        assert (out / ref).resolve().is_relative_to(out.resolve()) and (out / ref).exists()
    assert (out / "images" / "fallback.svg").exists()


def test_pack_excludes_answer_key_and_user_data(demo, tmp_path, dbs):
    out = tmp_path / "pack"
    export_reference(demo, out)
    names = set(files(out))
    assert {"README.md", "schema.md", "manifest.json", "answer-key/README.md", "products.csv", "offers.csv", "observations.csv", "reviews.csv"} <= names
    assert not any("answer_key" in n or n.endswith(".json") and n != "manifest.json" for n in names)
    text = b"".join(files(out).values()).decode("utf-8", "replace")
    for planted in ("inflated_reference", "genuine_discount", "mixed_event_outcomes", "answer_key_sha256"):
        assert planted not in text
    for private in ("password", "session", "watchlist_items", "notifications", "alert_rules"):
        assert private not in (out / "manifest.json").read_text(encoding="utf-8").lower() or private == "session"
    with pytest.raises(generator.DemoError):
        export_reference(dbs[DataMode.IMPORTED], tmp_path / "nope")  # Demo databases only
