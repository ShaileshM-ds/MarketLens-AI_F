"""Demo product photos: openly licensed, stored locally, credited, and mapped by category."""

import hashlib
import json
from pathlib import Path

from marketlens_core.demo import artwork, photos

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "frontend" / "public" / "demo-photos"


def test_every_photo_is_local_licensed_credited_and_unchanged():
    credits = json.loads((DIR / "credits.json").read_text(encoding="utf-8"))
    assert credits and {p.name for p in DIR.glob("*.jpg")} == {c["file"] for c in credits}
    for c in credits:
        data = (DIR / c["file"]).read_bytes()
        assert data[:3] == b"\xff\xd8\xff" and hashlib.sha256(data).hexdigest() == c["sha256"]
        assert c["license"].startswith(("CC0", "CC BY")) and c["author"] and c["source"].startswith("https://commons.wikimedia.org/")
        assert c["license"] == "CC0" or c["license_url"].startswith("https://creativecommons.org/")


def test_mapping_covers_demo_products_by_category_and_matches_the_generated_module():
    m = photos.demo_photo_map()
    cats = {c["category"] for c in json.loads((DIR / "credits.json").read_text(encoding="utf-8"))}
    for p in artwork.demo_products():
        if p["category"] in cats:
            assert m[p["product_id"]]["src"].startswith("/demo-photos/") and m[p["product_id"]]["src"].endswith(".jpg")
        else:
            assert p["product_id"] not in m  # e.g. phones keep their local artwork
    ts = (ROOT / "frontend" / "src" / "lib" / "demoPhotos.ts").read_text(encoding="utf-8")
    assert ts == photos.render_ts(m)  # the committed module is exactly what the generator produces
    assert "http://" not in ts and all(v["src"].startswith("/") for v in m.values())
