"""Every Demo product has local, self-contained artwork; nothing loads from an external host."""

import re
from pathlib import Path

import pytest

from helpers import NOW
from marketlens_core.demo import artwork, generator
from marketlens_core.settings import DataMode

IMAGES = Path(__file__).resolve().parents[1] / "frontend" / "public" / "demo-images"


def _external(svg: str) -> bool:
    body = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    return bool(re.search(r"https?://|<image|href=|url\((?!#)|@import", body))


def test_artwork_files_match_the_generator_and_are_self_contained():
    files = sorted(p.name for p in IMAGES.glob("*.svg"))
    expected = sorted([f'{p["product_id"]}.svg' for p in artwork.demo_products()] + [artwork.FALLBACK])
    assert files == expected
    for p in artwork.demo_products():
        svg = (IMAGES / f'{p["product_id"]}.svg').read_text(encoding="utf-8")
        assert svg == artwork.product_svg(p)  # committed files are exactly what the generator produces
        assert not _external(svg) and "demo artwork" in svg
    assert not _external((IMAGES / artwork.FALLBACK).read_text(encoding="utf-8"))
    assert len({artwork.product_svg(p) for p in artwork.demo_products()}) == 40  # no two cards look identical


@pytest.mark.integration
def test_every_generated_demo_product_has_artwork(dbs, tmp_path):
    db = dbs[DataMode.DEMO]
    generator.generate_demo(db, export_dir=tmp_path, now=NOW)
    for p in db.products.find({}, {"_id": 1, "colour": 1, "brand": 1}):
        meta = next(x for x in artwork.demo_products() if x["product_id"] == p["_id"])
        assert (IMAGES / f'{p["_id"]}.svg').exists() and meta["colour"] == p["colour"] and meta["brand"] == p["brand"]
