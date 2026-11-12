"""Which imported product image URLs may be shown in the browser.

The importer keeps every supplied URL unchanged on the product (`image.source_url`, provenance). The API
sends a URL to the browser only when it is safe to load:
- https only (never http, data:, javascript: or other schemes), with a real host and no embedded credentials,
  at most 2,048 characters;
- or a path to an image file the app itself serves (`/demo-images/` or `/demo-photos/<name>.svg|png|jpg|jpeg|webp`);
- the host matches the administrator's allowlist (`IMAGE_HOSTS`): "*" allows any https host, a
  comma-separated list allows those hosts and their subdomains, and an empty value shows no external images.
The page sends no referrer to image hosts (Referrer-Policy: same-origin) and falls back to the local
generic image when an image fails to load.
"""

import re
from urllib.parse import urlparse

from pymongo.database import Database

from .db import PRODUCTS

MAX_URL = 2048
# Image files the app itself serves (frontend/public/demo-images and demo-photos): same origin, offline, allowed under any policy.
APP_IMAGE_PATH = re.compile(r"^/(demo-images|demo-photos)/[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*\.(svg|png|jpg|jpeg|webp)$")


def displayable_url(url: str | None, policy: str) -> str | None:
    if not url or not isinstance(url, str) or len(url) > MAX_URL:
        return None
    if url.startswith("/"):
        return url if APP_IMAGE_PATH.match(url) and ".." not in url else None
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        return None
    host = p.hostname.lower()
    policy = (policy or "").strip()
    if policy == "*":
        return url.strip()
    allowed = {h.strip().lower().lstrip(".") for h in policy.split(",") if h.strip()}
    if host in allowed or any(host.endswith("." + h) for h in allowed):
        return url.strip()
    return None


def attach_image_urls(db: Database, items: list[dict], policy: str) -> None:
    """Adds `image.url` (or None) to each item that has a `product_id`, reading the stored source URL."""
    ids = [i["product_id"] for i in items if i.get("product_id")]
    if not ids:
        return
    stored = {p["_id"]: (p.get("image") or {}).get("source_url") for p in db[PRODUCTS].find({"_id": {"$in": ids}}, {"image": 1})}
    for i in items:
        i["image"] = {**(i.get("image") or {}), "url": displayable_url(stored.get(i.get("product_id")), policy)}
