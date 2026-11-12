"""Imported product image URLs are shown while browsing, but only safe ones: https, a real host, no
embedded credentials, and (optionally) an administrator's host allowlist. Others stay stored, never sent."""

import pytest
from fastapi.testclient import TestClient

from conftest import p5_import, p5_row
from helpers import NOW
from marketlens_core.images import displayable_url

pytestmark = pytest.mark.integration
Q = {"mode": "imported"}
GOOD = "https://images.example-cdn.com/products/tee-black.jpg"


def test_displayable_url_rules():
    assert displayable_url(GOOD, "*") == GOOD
    assert displayable_url("http://images.example-cdn.com/a.jpg", "*") is None  # never insecure http
    assert displayable_url("javascript:alert(1)", "*") is None
    assert displayable_url("data:image/png;base64,AAAA", "*") is None
    assert displayable_url("https://user:pass@images.example-cdn.com/a.jpg", "*") is None
    assert displayable_url("https:///nohost.jpg", "*") is None
    assert displayable_url(None, "*") is None and displayable_url("", "*") is None
    assert displayable_url("https://x.com/" + "a" * 3000, "*") is None
    assert displayable_url(GOOD, "example-cdn.com") == GOOD  # subdomains of an allowed host
    assert displayable_url(GOOD, "other.com, cdn.example.org") is None
    assert displayable_url("https://evil-example-cdn.com/a.jpg", "example-cdn.com") is None
    assert displayable_url(GOOD, "") is None  # empty allowlist: show none


def test_app_served_image_paths_are_shown_and_nothing_else_relative():
    # Files the app itself serves (the example dataset's artwork) work offline and under any host policy.
    assert displayable_url("/demo-images/DEMO-P-001.svg", "") == "/demo-images/DEMO-P-001.svg"
    assert displayable_url("/demo-images/fallback.svg", "*") == "/demo-images/fallback.svg"
    assert displayable_url("/demo-photos/home-appliances-1.jpg", "") == "/demo-photos/home-appliances-1.jpg"
    assert displayable_url("/demo-photos/../credits.json", "*") is None and displayable_url("/demo-photos/credits.json", "*") is None
    for bad in ("/demo-images/../index.html", "/demo-images/a b.svg", "/api/v1/products", "//evil.com/a.svg",
                "/demo-images/x.svg?y=1", "/demo-images/x.html", "demo-images/x.svg", "/demo-images/sub/x.svg"):
        assert displayable_url(bad, "*") is None, bad


@pytest.fixture
def imaged(p5):
    p5_import(p5.db, p5.settings, [
        p5_row("L-I1", "Amazon", "999", "40", pid="IMG-1", product_name="Imaged tee", image_url=GOOD),
        p5_row("L-I2", "Amazon", "899", "40", pid="IMG-2", product_name="Insecure tee", image_url="http://images.example-cdn.com/b.jpg"),
        p5_row("L-I3", "Amazon", "799", "40", pid="IMG-3", product_name="No image tee", image_url=""),
    ], NOW, name="images.csv")
    return p5


def _items(client):
    return {i["product_id"]: i for i in client.get("/api/v1/products", params={**Q, "page_size": 60}).json()["items"]}


def test_explorer_detail_and_compare_send_only_safe_urls(imaged):
    items = _items(imaged.anon)
    assert items["IMG-1"]["image"]["url"] == GOOD
    assert items["IMG-2"]["image"]["url"] is None and items["IMG-3"]["image"]["url"] is None
    d = imaged.anon.get("/api/v1/products/IMG-1", params=Q).json()
    assert d["product"]["image"]["url"] == GOOD
    c = imaged.anon.get("/api/v1/compare", params={**Q, "ids": ["IMG-1", "IMG-2"]}).json()
    assert {p["product_id"]: p["image"]["url"] for p in c["products"]} == {"IMG-1": GOOD, "IMG-2": None}
    # The stored record keeps the original URL either way (provenance), and nothing in Demo changes.
    assert imaged.db.products.find_one({"_id": "IMG-2"})["image"]["source_url"] == "http://images.example-cdn.com/b.jpg"


def test_administrator_allowlist_restricts_hosts(imaged):
    from app.main import create_app

    for policy, expected in (("example-cdn.com", GOOD), ("cdn.other.org", None), ("", None)):
        with TestClient(create_app(imaged.settings.model_copy(update={"image_hosts": policy}))) as c:
            assert _items(c)["IMG-1"]["image"]["url"] == expected, policy
