"""Verified price history with an explicit UTC cutoff (CLAUDE.md: every historical analysis takes a cutoff).

Only `history_eligible` observations (verified UTC time) are used. Timezone-unknown snapshots are counted
as excluded and never become history. Nothing observed after the cutoff is read. Missing days are gaps,
never filled. A day's value for a listing is the lowest value observed that day up to the cutoff; the
product line is the lowest listing value that day. Values are integer minor units in one currency.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from pymongo.database import Database

from .db import OBSERVATIONS, OFFERS, PRODUCTS
from .pricing import delivered_price

WINDOWS = (7, 30, 90, 180)
BASES = ("base", "delivered")
UTC = timezone.utc
HISTORY_UNAVAILABLE = (
    "Verified historical price data is not available for this product yet. "
    "Current comparisons use imported snapshot observations."
)
COMPARED_FIELDS = (
    "price_minor", "reference_price_minor", "shipping_minor", "availability", "stock_quantity", "advertised_discount_percent",
    "coupon_discount_minor", "payment_offer", "urgency_message", "seller_rating", "product_rating",
)
_PROJ = {"raw": 0, "content_hash": 0}


class HistoryError(ValueError):
    pass


def require_utc(dt, name: str) -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise HistoryError(f"{name} must be an explicit UTC time, for example 2026-10-15T12:00:00Z.")
    return dt.astimezone(UTC)


def parse_utc(text: str, name: str) -> datetime:
    try:
        dt = datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
    except ValueError:
        raise HistoryError(f"{name} '{text}' is not an ISO 8601 date and time.") from None
    return require_utc(dt, name)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def _iso(dt):
    return None if dt is None else _aware(dt).isoformat().replace("+00:00", "Z")


def _value(o: dict, basis: str):
    if basis == "base":
        return o.get("price_minor")
    return delivered_price(o.get("price_minor"), o.get("shipping_minor"), bool(o.get("shipping_known")))


def product_history(db: Database, product_id: str, *, cutoff: datetime, window_days: int, basis: str = "base", marketplace: str | None = None) -> dict | None:
    cutoff = require_utc(cutoff, "cutoff")
    if window_days not in WINDOWS:
        raise HistoryError(f"window must be one of {', '.join(map(str, WINDOWS))} days.")
    if basis not in BASES:
        raise HistoryError("basis must be 'base' or 'delivered'.")
    product = db[PRODUCTS].find_one({"_id": product_id}, {"name": 1, "synthetic": 1})
    if not product:
        return None
    offers = list(db[OFFERS].find({"product_id": product_id}).sort("_id", 1))
    if marketplace:
        offers = [o for o in offers if o.get("marketplace") == marketplace]
    lids = [o["_id"] for o in offers]
    start_day = cutoff.date() - timedelta(days=window_days - 1)
    start = datetime.combine(start_day, time.min, UTC)
    scope = {"product_id": product_id, "listing_id": {"$in": lids}}
    tz_unknown = db[OBSERVATIONS].count_documents({**scope, "timestamp_quality": "timezone_unknown"})
    verified_before_cutoff = db[OBSERVATIONS].count_documents({**scope, "history_eligible": True, "observed_at": {"$lte": cutoff}})
    rows = list(db[OBSERVATIONS].find({**scope, "history_eligible": True, "observed_at": {"$gte": start, "$lte": cutoff}}, _PROJ).sort([("observed_at", 1), ("_id", 1)]))

    currencies = sorted({o.get("currency") for o in rows if o.get("currency")})
    base = {
        "product_id": product_id,
        "cutoff": _iso(cutoff),
        "window": {"days": window_days, "start": _iso(start), "end": _iso(cutoff)},
        "basis": basis,
        "marketplace": marketplace,
        "currency": currencies[0] if len(currencies) == 1 else None,
        "excluded": {"timezone_unknown": tz_unknown, "unknown_shipping_observations": 0},
        "source": {"synthetic": all(o.get("synthetic") for o in rows) if rows else bool(product.get("synthetic")),
                   "source_labels": sorted({o.get("source_label") for o in rows if o.get("source_label")})},
        "series": [],
        "listings": [],
        "coverage": {"days_in_window": window_days, "days_with_data": 0, "first_date": None, "last_date": None, "missing_dates": []},
    }
    if verified_before_cutoff == 0:
        return {**base, "status": "unavailable", "reason": HISTORY_UNAVAILABLE}
    if len(currencies) > 1:
        return {**base, "status": "unavailable", "reason": f"Observations use different currencies ({', '.join(currencies)}); they aren't combined."}

    per_listing: dict[str, dict[date, list[int]]] = defaultdict(lambda: defaultdict(list))
    unknown = 0
    for o in rows:
        v = _value(o, basis)
        if v is None:
            unknown += 1
            continue
        per_listing[o["listing_id"]][_aware(o["observed_at"]).date()].append(v)
    base["excluded"]["unknown_shipping_observations"] = unknown

    listings, by_date = [], defaultdict(list)
    for off in offers:
        days = per_listing.get(off["_id"], {})
        pts = [{"date": d.isoformat(), "value_minor": min(vs), "observations": len(vs)} for d, vs in sorted(days.items())]
        for p in pts:
            by_date[p["date"]].append((p["value_minor"], off.get("marketplace")))
        listings.append({"listing_id": off["_id"], "marketplace": off.get("marketplace"), "seller_id": off.get("seller_id"), "points": pts})
    series = []
    for d in sorted(by_date):
        low = min(v for v, _ in by_date[d])
        series.append({"date": d, "value_minor": low, "marketplaces": sorted({m for v, m in by_date[d] if v == low})})

    if series:
        first, last = date.fromisoformat(series[0]["date"]), date.fromisoformat(series[-1]["date"])
        have = {p["date"] for p in series}
        missing = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1) if (first + timedelta(days=i)).isoformat() not in have]
        base["coverage"].update({"days_with_data": len(series), "first_date": series[0]["date"], "last_date": series[-1]["date"], "missing_dates": missing})
    status, reason = "available", None
    if len(series) < 2:
        status = "insufficient"
        reason = "Fewer than two days of verified observations in this window." if series else "No verified observations in this window."
    return {**base, "series": series, "listings": listings, "status": status, "reason": reason}


def _obs_view(o: dict | None) -> dict | None:
    if o is None:
        return None
    return {
        "observed_at": _iso(o.get("observed_at")),
        "source_timestamp": o.get("source_timestamp"),
        "currency": o.get("currency"),
        "price_minor": o.get("price_minor"),
        "reference_price_minor": o.get("reference_price_minor"),
        "shipping_minor": o.get("shipping_minor"),
        "shipping_known": bool(o.get("shipping_known")),
        "delivered_price_minor": _value(o, "delivered"),
        "advertised_discount_percent": o.get("advertised_discount_percent"),
        "coupon_discount_minor": o.get("coupon_discount_minor"),
        "payment_offer": o.get("payment_offer"),
        "availability": o.get("availability"),
        "stock_quantity": o.get("stock_quantity"),
        "urgency_message": o.get("urgency_message"),
        "seller_rating": o.get("seller_rating"),
        "product_rating": o.get("product_rating"),
        "flags": o.get("flags") or [],
        "synthetic": o.get("synthetic"),
        "source_label": o.get("source_label"),
    }


def as_of(db: Database, product_id: str, *, at: datetime) -> dict | None:
    """Observed state at a time: per listing the latest verified observation at or before `at`.
    Nothing after `at` is read or returned (no 'next' observation)."""
    at = require_utc(at, "at")
    if not db[PRODUCTS].find_one({"_id": product_id}, {"_id": 1}):
        return None
    out = []
    for off in db[OFFERS].find({"product_id": product_id}).sort("_id", 1):
        two = list(db[OBSERVATIONS].find({"listing_id": off["_id"], "history_eligible": True, "observed_at": {"$lte": at}}, _PROJ)
                   .sort([("observed_at", -1), ("_id", -1)]).limit(2))
        cur = two[0] if two else None
        prev = two[1] if len(two) > 1 else None
        changed = [f for f in COMPARED_FIELDS if cur and prev and cur.get(f) != prev.get(f)]
        out.append({
            "listing_id": off["_id"],
            "marketplace": off.get("marketplace"),
            "seller_id": off.get("seller_id"),
            "seller_name": off.get("seller_name"),
            "observation": _obs_view(cur),
            "previous": _obs_view(prev),
            "age_seconds": int((at - _aware(cur["observed_at"])).total_seconds()) if cur else None,
            "changed_fields": changed,
            "reason": None if cur else "No verified observation at or before this time.",
        })
    tz_unknown = db[OBSERVATIONS].count_documents({"product_id": product_id, "timestamp_quality": "timezone_unknown"})
    return {"product_id": product_id, "requested_at": _iso(at), "listings": out, "excluded": {"timezone_unknown": tz_unknown}}
