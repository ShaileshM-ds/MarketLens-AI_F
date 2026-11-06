"""Product Explorer: read model, listing queries, product details and reviews.

Source collections (products, offers, observations, reviews) are only READ here.
The one write is the derived `product_summaries` read model, rebuilt from those
collections so list endpoints never read every observation per request
(docs/SCOPE.md §8). It can be dropped and rebuilt at any time without data loss.

Current observation per offer (docs/DECISIONS.md):
  1. Any verified UTC observations  -> the latest by observed_at ("latest_verified_utc").
  2. Otherwise exactly one snapshot -> that snapshot ("single_snapshot_timezone_unknown").
  3. Otherwise several snapshots without timezones -> none; they can't be ordered
     ("ambiguous_unordered_snapshots").
"""

import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse

from pymongo import ReplaceOne
from pymongo.database import Database

from .catalog import LAUNCH_CATEGORIES
from .db import OBSERVATIONS, OFFERS, PRODUCTS, REVIEWS
from .pricing import delivered_price, discount_analysis, lowest_designations

SUMMARIES = "product_summaries"
SUMMARY_VERSION = 2  # v2 adds delivered price, discount and availability fields per listing
CATEGORY_LABELS = {c.slug: c.label for c in LAUNCH_CATEGORIES}
CATEGORY_ORDER = [c.slug for c in LAUNCH_CATEGORIES]

AVAILABILITY_LABELS = {
    "in_stock": "In stock",
    "limited_stock": "Limited stock",
    "out_of_stock": "Out of stock",
    "unknown": "Not stated",
}
SORTS = (
    "name_asc", "name_desc", "price_asc", "price_desc", "delivered_asc", "delivered_desc",
    "rating_desc", "discount_desc", "available_desc", "offers_desc",
)

QUALITY_LABELS = {
    "synthetic_dataset": ("Synthetic dataset", "Generated demonstration data, not real marketplace records."),
    "timezone_unknown": ("Timezone unknown", "Observation times have no timezone, so they can't form a verified price history."),
    "shipping_unknown": ("Shipping unknown", "At least one listing doesn't state shipping, so its delivered total can't be confirmed."),
    "availability_contradiction": ("Availability contradiction", "At least one listing's stated availability disagrees with its stock quantity."),
    "missing_product_metadata": ("Missing product metadata", "Brand, size and colour aren't supplied; they are never guessed from the name."),
    "verified_history": ("Verified historical observation", "At least one observation has a verified UTC timestamp."),
}

WARNING_MESSAGES = {
    "stock_availability_contradiction": "Availability and reported stock quantity disagree.",
    "price_above_reference": "The price is above the stated reference price.",
    "discount_mismatch": "The advertised discount doesn't match the difference from the reference price.",
    "shipping_unknown": "Shipping cost isn't stated, so the delivered total is unknown.",
    "timezone_unknown": "The observation time has no timezone, so it can't be part of a verified price history.",
    "ambiguous_unordered_snapshots": "This listing has several snapshots without timezones, so the current one can't be determined.",
    "no_observation": "No observation is stored for this listing.",
}
HISTORY_UNAVAILABLE = (
    "Verified historical price data is not available for this product yet. "
    "Current comparisons use imported snapshot observations."
)
HISTORY_NOT_BUILT = "Verified UTC observations are available for this product. Snapshot observations without a timezone are not part of its history."
REVIEW_FORMULA = (
    "Arithmetic mean of the individual review ratings (1 to 5) for this product across all stores, "
    "rounded to 2 decimals. Product ratings and seller ratings are not included."
)


# ---------- pure helpers ----------
def availability_class(text: str | None) -> str:
    t = (text or "").strip().lower()
    return {"in stock": "in_stock", "limited stock": "limited_stock", "out of stock": "out_of_stock"}.get(t, "unknown")


def select_current(observations: list[dict]) -> tuple[dict | None, str]:
    if not observations:
        return None, "no_observation"
    verified = [o for o in observations if o.get("observed_at") is not None and o.get("history_eligible")]
    if verified:
        return max(verified, key=lambda o: (o["observed_at"], o["_id"])), "latest_verified_utc"
    if len(observations) == 1:
        return observations[0], "single_snapshot_timezone_unknown"
    return None, "ambiguous_unordered_snapshots"


def _warning(code: str) -> dict:
    return {"code": code, "message": WARNING_MESSAGES[code]}


def offer_view(o: dict | None, basis: str | None = None) -> dict:
    """Observation-level fields for one offer. Unknown stays None; nothing is subtracted or corrected."""
    if o is None:
        return {
            "currency": None, "price_minor": None, "reference_price_minor": None, "advertised_discount_percent": None,
            "shipping_minor": None, "shipping_known": False, "total_minor": None, "free_shipping": False,
            "coupon_discount_minor": None, "payment_offer": None, "availability": None, "availability_class": "unknown",
            "stock_quantity": None, "seller_rating": None, "product_rating": None, "delivery_information": None,
            "urgency_message": None, "seller_location": None, "condition": None,
            "warnings": [_warning(basis or "no_observation")], "purchasable": False,
            "flags": [], "delivered_price_minor": None, "delivered_status": "no_price",
            "discount": discount_analysis(None, None, None),
        }
    price = o.get("price_minor")
    shipping = o.get("shipping_minor") if o.get("shipping_known") else None
    flags = list(o.get("flags") or [])
    cls = availability_class(o.get("availability"))
    warnings = [_warning(f) for f in flags if f in WARNING_MESSAGES]
    if not o.get("shipping_known"):
        warnings.append(_warning("shipping_unknown"))
    if o.get("timestamp_quality") == "timezone_unknown":
        warnings.append(_warning("timezone_unknown"))
    return {
        "currency": o.get("currency"),
        "price_minor": price,
        "reference_price_minor": o.get("reference_price_minor"),
        "advertised_discount_percent": o.get("advertised_discount_percent"),
        "shipping_minor": shipping,
        "shipping_known": bool(o.get("shipping_known")),
        "total_minor": price + shipping if price is not None and shipping is not None else None,
        "free_shipping": shipping == 0,
        "coupon_discount_minor": o.get("coupon_discount_minor"),  # conditional; never subtracted
        "payment_offer": o.get("payment_offer"),  # conditional; never subtracted
        "availability": o.get("availability"),
        "availability_class": cls,
        "stock_quantity": o.get("stock_quantity"),
        "seller_rating": o.get("seller_rating"),
        "product_rating": o.get("product_rating"),
        "delivery_information": o.get("delivery_information"),
        "urgency_message": o.get("urgency_message"),
        "seller_location": o.get("seller_location"),
        "condition": o.get("condition"),
        "warnings": warnings,
        "purchasable": price is not None
        and cls in ("in_stock", "limited_stock")
        and "stock_availability_contradiction" not in flags,
        "flags": flags,
        "delivered_price_minor": delivered_price(price, shipping, bool(o.get("shipping_known"))),
        "delivered_status": "no_price" if price is None else ("confirmed" if shipping is not None else "cannot_be_confirmed"),
        "discount": discount_analysis(price, o.get("reference_price_minor"), o.get("advertised_discount_percent")),
    }


def _safe_url(url: str | None) -> str | None:
    return url if url and urlparse(url).scheme in ("http", "https") else None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------- read model ----------
_OBS_PROJECTION = {"raw": 0, "content_hash": 0, "provenance": 0}


def _load(db: Database, products: list[dict]):
    pids = [p["_id"] for p in products]
    offers = list(db[OFFERS].find({"product_id": {"$in": pids}}).sort("_id", 1))
    by_listing = defaultdict(list)
    lids = [o["_id"] for o in offers]
    for i in range(0, len(lids), 1000):
        for ob in db[OBSERVATIONS].find({"listing_id": {"$in": lids[i : i + 1000]}}, _OBS_PROJECTION):
            by_listing[ob["listing_id"]].append(ob)
    offers_by_product = defaultdict(list)
    for o in offers:
        offers_by_product[o["product_id"]].append(o)
    review_counts = {
        d["_id"]: d["n"]
        for d in db[REVIEWS].aggregate([{"$match": {"product_id": {"$in": pids}}}, {"$group": {"_id": "$product_id", "n": {"$sum": 1}}}])
    }
    return offers_by_product, by_listing, review_counts


def build_summary(product: dict, offers: list[dict], obs_by_listing: dict, review_count: int, now: datetime) -> dict:
    entries, verified, unknown_tz, warn = [], 0, 0, False
    for off in sorted(offers, key=lambda o: o["_id"]):
        group = obs_by_listing.get(off["_id"], [])
        verified += sum(1 for g in group if g.get("history_eligible"))
        unknown_tz += sum(1 for g in group if g.get("timestamp_quality") == "timezone_unknown")
        cur, basis = select_current(group)
        v = offer_view(cur, basis)
        warn = warn or any(w["code"] != "timezone_unknown" for w in v["warnings"])
        entries.append(
            {
                "listing_id": off["_id"],
                "marketplace": off.get("marketplace"),
                "has_current": cur is not None,
                "basis": basis,
                "currency": v["currency"],
                "price_minor": v["price_minor"],
                "shipping_minor": v["shipping_minor"],
                "shipping_known": v["shipping_known"],
                "availability_class": v["availability_class"],
                "seller_rating": v["seller_rating"],
                "product_rating": v["product_rating"],
                "condition": v["condition"] or off.get("condition"),
                "flags": v["flags"],
                "delivered_minor": v["delivered_price_minor"],
                "advertised_discount_percent": v["advertised_discount_percent"],
                "available": v["purchasable"],
            }
        )
    return {
        "_id": product["_id"],
        "product_id": product["_id"],
        "product_id_lower": product["_id"].lower(),
        "name": product.get("name"),
        "name_lower": (product.get("name") or "").lower(),
        "category": product.get("category"),
        "source_category": product.get("source_category"),
        "brand": product.get("brand"),
        "size": product.get("size"),
        "colour": product.get("colour"),
        "image_kind": (product.get("image") or {}).get("kind", "none"),
        "synthetic": product.get("synthetic"),
        "source_label": product.get("source_label"),
        "offer_count": len(entries),
        "review_count": review_count,
        "offers": entries,
        "has_data_warnings": warn,
        "verified_observation_count": verified,
        "timezone_unknown_observation_count": unknown_tz,
        "summary_version": SUMMARY_VERSION,
        "built_at": now,
    }


def rebuild_product_summaries(db: Database, product_ids=None, now: datetime | None = None) -> int:
    """Rebuild summaries for the given products (all when None). Writes only `product_summaries`."""
    now = now or datetime.now(timezone.utc)
    query = {} if product_ids is None else {"_id": {"$in": list(product_ids)}}
    written = 0
    batch: list[dict] = []

    def flush():
        nonlocal written
        if not batch:
            return
        offers_by_product, by_listing, review_counts = _load(db, batch)
        ops = [
            ReplaceOne(
                {"_id": p["_id"]},
                build_summary(p, offers_by_product.get(p["_id"], []), by_listing, review_counts.get(p["_id"], 0), now),
                upsert=True,
            )
            for p in batch
        ]
        db[SUMMARIES].bulk_write(ops, ordered=False)
        written += len(ops)
        batch.clear()

    for p in db[PRODUCTS].find(query).sort("_id", 1):
        batch.append(p)
        if len(batch) >= 500:
            flush()
    flush()
    return written


def ensure_summaries_current(db: Database) -> int:
    """Rebuild the read model only if it is missing products or built by an older version. Returns rebuilt count."""
    products = db[PRODUCTS].count_documents({})
    current = db[SUMMARIES].count_documents({"summary_version": SUMMARY_VERSION})
    if products == current and db[SUMMARIES].count_documents({}) == products:
        return 0
    return rebuild_product_summaries(db)


# ---------- listing ----------
def _offer_conditions(f: dict) -> tuple[dict, list]:
    q, e = {}, []
    if f.get("marketplaces"):
        q["marketplace"] = {"$in": f["marketplaces"]}
        e.append({"$in": ["$$o.marketplace", f["marketplaces"]]})
    if f.get("currency"):
        q["currency"] = f["currency"]
        e.append({"$eq": ["$$o.currency", f["currency"]]})
    if f.get("price_min") is not None or f.get("price_max") is not None:
        rng = {}
        e.append({"$ne": ["$$o.price_minor", None]})
        if f.get("price_min") is not None:
            rng["$gte"] = f["price_min"]
            e.append({"$gte": ["$$o.price_minor", f["price_min"]]})
        if f.get("price_max") is not None:
            rng["$lte"] = f["price_max"]
            e.append({"$lte": ["$$o.price_minor", f["price_max"]]})
        q["price_minor"] = rng
    if f.get("availability"):
        q["availability_class"] = {"$in": f["availability"]}
        e.append({"$in": ["$$o.availability_class", f["availability"]]})
    for key, field in (("seller_rating_min", "seller_rating"), ("product_rating_min", "product_rating")):
        if f.get(key) is not None:
            q[field] = {"$gte": f[key]}
            e.append({"$ne": [f"$$o.{field}", None]})
            e.append({"$gte": [f"$$o.{field}", f[key]]})
    if f.get("free_shipping"):
        q["shipping_known"] = True
        q["shipping_minor"] = 0
        e.append({"$eq": ["$$o.shipping_known", True]})
        e.append({"$eq": ["$$o.shipping_minor", 0]})
    if f.get("condition"):
        q["condition"] = f["condition"]
        e.append({"$eq": ["$$o.condition", f["condition"]]})
    if f.get("discount_min") is not None or f.get("discount_max") is not None:
        rng = {}
        e.append({"$ne": ["$$o.advertised_discount_percent", None]})
        if f.get("discount_min") is not None:
            rng["$gte"] = f["discount_min"]
            e.append({"$gte": ["$$o.advertised_discount_percent", f["discount_min"]]})
        if f.get("discount_max") is not None:
            rng["$lte"] = f["discount_max"]
            e.append({"$lte": ["$$o.advertised_discount_percent", f["discount_max"]]})
        q["advertised_discount_percent"] = rng
    if f.get("delivered_known"):
        q["delivered_minor"] = {"$ne": None}
        e.append({"$ne": [{"$ifNull": ["$$o.delivered_minor", None]}, None]})
    return q, e


_SORT_SPECS = {
    "name_asc": {"name_lower": 1, "product_id": 1},
    "name_desc": {"name_lower": -1, "product_id": 1},
    "price_asc": {"has_lowest": -1, "lowest": 1, "name_lower": 1, "product_id": 1},
    "price_desc": {"has_lowest": -1, "lowest": -1, "name_lower": 1, "product_id": 1},
    "delivered_asc": {"has_delivered": -1, "lowest_delivered": 1, "name_lower": 1, "product_id": 1},
    "delivered_desc": {"has_delivered": -1, "lowest_delivered": -1, "name_lower": 1, "product_id": 1},
    "rating_desc": {"has_rating": -1, "max_rating": -1, "name_lower": 1, "product_id": 1},
    "discount_desc": {"has_discount": -1, "max_discount": -1, "name_lower": 1, "product_id": 1},
    "available_desc": {"acount": -1, "name_lower": 1, "product_id": 1},
    "offers_desc": {"mcount": -1, "name_lower": 1, "product_id": 1},
}


def _item(doc: dict) -> dict:
    m = doc["m"]
    priced = [o for o in m if o.get("price_minor") is not None]
    lowest = doc.get("lowest")
    lowest_price, reason = None, None
    if lowest is not None:
        lows = [o for o in priced if o["price_minor"] == lowest]
        lowest_price = {
            "amount_minor": lowest,
            "currency": priced[0]["currency"],
            "basis": "base_listing_price",
            "excludes_shipping": True,
            "marketplaces": sorted({o["marketplace"] for o in lows}),
            "offers_with_unknown_shipping": sum(1 for o in m if o.get("has_current") and not o.get("shipping_known")),
            "out_of_stock": all(o.get("availability_class") == "out_of_stock" for o in lows),
        }
    elif priced:
        currencies = sorted({o["currency"] for o in priced})
        reason = f"Matching listings use different currencies ({', '.join(currencies)}); prices aren't compared across currencies."
    else:
        reason = "No current price is available for the matching listings."
    avail = {k: 0 for k in AVAILABILITY_LABELS}
    for o in m:
        avail[o.get("availability_class", "unknown")] += 1
    ratings = [o["product_rating"] for o in m if o.get("product_rating") is not None]
    return {
        "product_id": doc["product_id"],
        "name": doc["name"],
        "category": doc["category"],
        "category_label": CATEGORY_LABELS.get(doc["category"], doc["category"]),
        "source_category": doc.get("source_category"),
        "brand": doc.get("brand"),
        "size": doc.get("size"),
        "colour": doc.get("colour"),
        "image": {"kind": doc.get("image_kind", "none")},
        "synthetic": doc.get("synthetic"),
        "source_label": doc.get("source_label"),
        "offer_count": doc.get("offer_count", 0),
        "matching_offer_count": len(m),
        "matching_marketplaces": sorted({o["marketplace"] for o in m}),
        "lowest_price": lowest_price,
        "lowest_price_unavailable_reason": reason,
        "availability": avail,
        "product_rating": {"min": min(ratings), "max": max(ratings), "stores": len(ratings)} if ratings else None,
        "review_count": doc.get("review_count", 0),
        "has_data_warnings": bool(doc.get("has_data_warnings")),
        "verified_history": doc.get("verified_observation_count", 0) > 0,
        "lowest_delivered": _lowest_delivered(m),
        "available_offer_count": sum(1 for o in m if o.get("available")),
        "max_advertised_discount": max((o["advertised_discount_percent"] for o in m if o.get("advertised_discount_percent") is not None), default=None),
    }


def _lowest_delivered(m: list[dict]) -> dict | None:
    """Lowest confirmed delivered price among the matching listings (any availability)."""
    d = lowest_designations(m)["lowest_confirmed_delivered"]
    if d["amount_minor"] is None:
        return None
    return {
        "amount_minor": d["amount_minor"],
        "currency": d["currency"],
        "marketplaces": d["marketplaces"],
        "certain_overall": d["certain_overall"],
    }


def list_products(db: Database, *, filters: dict, sort: str, page: int, page_size: int) -> dict:
    match: dict = {}
    if filters.get("category"):
        match["category"] = filters["category"]
    q = (filters.get("q") or "").strip().lower()
    if q:
        match["$or"] = [{"product_id_lower": q}, {"name_lower": {"$regex": re.escape(q)}}]
    offer_q, offer_e = _offer_conditions(filters)
    if offer_q:
        match["offers"] = {"$elemMatch": offer_q}
    m_expr = {"$filter": {"input": "$offers", "as": "o", "cond": {"$and": offer_e}}} if offer_e else "$offers"
    pipeline = [
        {"$match": match},
        {"$addFields": {"m": m_expr}},
        {"$addFields": {"priced": {"$filter": {"input": "$m", "as": "o", "cond": {"$ne": ["$$o.price_minor", None]}}}}},
        {"$addFields": {"pcur": {"$setUnion": ["$priced.currency", []]}}},
        {
            "$addFields": {
                "lowest": {"$cond": [{"$eq": [{"$size": "$pcur"}, 1]}, {"$min": "$priced.price_minor"}, None]},
                # Confirmed delivered = base + known shipping; never compared across currencies.
                "lowest_delivered": {"$cond": [{"$eq": [{"$size": "$pcur"}, 1]}, {"$min": "$m.delivered_minor"}, None]},
                "max_rating": {"$max": "$m.product_rating"},
                "max_discount": {"$max": "$m.advertised_discount_percent"},
                "mcount": {"$size": "$m"},
                "acount": {"$size": {"$filter": {"input": "$m", "as": "o", "cond": {"$eq": ["$$o.available", True]}}}},
            }
        },
        {
            "$addFields": {
                "has_lowest": {"$cond": [{"$eq": ["$lowest", None]}, 0, 1]},
                "has_delivered": {"$cond": [{"$eq": [{"$ifNull": ["$lowest_delivered", None]}, None]}, 0, 1]},
                "has_rating": {"$cond": [{"$eq": ["$max_rating", None]}, 0, 1]},
                "has_discount": {"$cond": [{"$eq": [{"$ifNull": ["$max_discount", None]}, None]}, 0, 1]},
            }
        },
        {"$sort": _SORT_SPECS[sort]},
        {"$facet": {"total": [{"$count": "n"}], "items": [{"$skip": (page - 1) * page_size}, {"$limit": page_size}]}},
    ]
    res = next(db[SUMMARIES].aggregate(pipeline), {"total": [], "items": []})
    return {
        "total": res["total"][0]["n"] if res["total"] else 0,
        "page": page,
        "page_size": page_size,
        "sort": sort,
        "items": [_item(d) for d in res["items"]],
        "semantics": {
            "price": "Lowest current base listing price among the listings that match every store filter. Shipping, coupons and payment offers are not included.",
            "delivered": "Lowest confirmed delivered price (base price + known shipping) among matching listings. Listings with unknown shipping have no delivered price; coupons and payment offers are never subtracted.",
            "store_filters": "A product matches when at least one of its listings meets every store-level filter (marketplace, price, availability, ratings, free shipping) at the same time.",
            "history": "Snapshot observations without a timezone are not price history.",
        },
    }


def filter_metadata(db: Database) -> dict:
    total = db[PRODUCTS].count_documents({})
    summarized = db[SUMMARIES].count_documents({"summary_version": SUMMARY_VERSION})
    cats = {d["_id"]: d["n"] for d in db[SUMMARIES].aggregate([{"$group": {"_id": "$category", "n": {"$sum": 1}}}])}
    unwound = [{"$unwind": "$offers"}]
    markets = list(
        db[SUMMARIES].aggregate(
            unwound + [{"$group": {"_id": "$offers.marketplace", "p": {"$addToSet": "$_id"}}}, {"$project": {"n": {"$size": "$p"}}}, {"$sort": {"_id": 1}}]
        )
    )
    currencies = list(
        db[SUMMARIES].aggregate(
            unwound
            + [
                {"$match": {"offers.price_minor": {"$ne": None}}},
                {"$group": {"_id": "$offers.currency", "min": {"$min": "$offers.price_minor"}, "max": {"$max": "$offers.price_minor"}}},
                {"$sort": {"_id": 1}},
            ]
        )
    )
    avail = {d["_id"]: d["n"] for d in db[SUMMARIES].aggregate(unwound + [{"$group": {"_id": "$offers.availability_class", "n": {"$sum": 1}}}])}
    ratings = next(
        db[SUMMARIES].aggregate(
            unwound
            + [
                {
                    "$group": {
                        "_id": None,
                        "pmin": {"$min": "$offers.product_rating"},
                        "pmax": {"$max": "$offers.product_rating"},
                        "smin": {"$min": "$offers.seller_rating"},
                        "smax": {"$max": "$offers.seller_rating"},
                    }
                }
            ]
        ),
        {},
    )
    verified = db[SUMMARIES].count_documents({"verified_observation_count": {"$gt": 0}})
    unknown_tz = db[SUMMARIES].count_documents({"timezone_unknown_observation_count": {"$gt": 0}})
    nonsynthetic = db[SUMMARIES].count_documents({"synthetic": {"$ne": True}})

    def distinct(field):
        return sorted(v for v in db[SUMMARIES].distinct(field) if v not in (None, ""))

    return {
        "total_products": total,
        "categories": [{"slug": s, "label": CATEGORY_LABELS[s], "count": cats[s]} for s in CATEGORY_ORDER if cats.get(s)],
        "marketplaces": [{"name": d["_id"], "count": d["n"]} for d in markets if d["_id"]],
        "currencies": [{"code": d["_id"], "min_price_minor": d["min"], "max_price_minor": d["max"]} for d in currencies if d["_id"]],
        "availability": [{"value": k, "label": AVAILABILITY_LABELS[k], "count": avail[k]} for k in AVAILABILITY_LABELS if avail.get(k)],
        "conditions": distinct("offers.condition"),
        "brands": distinct("brand"),
        "sizes": distinct("size"),
        "colours": distinct("colour"),
        "product_rating_range": [ratings.get("pmin"), ratings.get("pmax")] if ratings.get("pmax") is not None else None,
        "seller_rating_range": [ratings.get("smin"), ratings.get("smax")] if ratings.get("smax") is not None else None,
        "sorts": list(SORTS),
        "catalog_status": {"products": total, "summarized": summarized, "up_to_date": summarized == total},
        "data_basis": {
            "verified_history": verified > 0,
            "snapshot_only": unknown_tz > 0 and verified == 0,
            "all_synthetic": total > 0 and nonsynthetic == 0,
        },
    }


# ---------- details ----------
def _round2(n: Decimal) -> float:
    return float(n.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _details(db: Database, product_ids: list[str]) -> dict[str, dict]:
    """Full details for several products with a fixed number of queries (no per-product round trips)."""
    products = {p["_id"]: p for p in db[PRODUCTS].find({"_id": {"$in": product_ids}})}
    if not products:
        return {}
    ids = list(products)
    offers_by_product = defaultdict(list)
    for o in db[OFFERS].find({"product_id": {"$in": ids}}).sort("_id", 1):
        offers_by_product[o["product_id"]].append(o)
    lids = [o["_id"] for offers in offers_by_product.values() for o in offers]
    groups = defaultdict(list)
    for i in range(0, len(lids), 1000):
        for ob in db[OBSERVATIONS].find({"listing_id": {"$in": lids[i : i + 1000]}}, _OBS_PROJECTION):
            groups[ob["listing_id"]].append(ob)
    ratings = defaultdict(list)
    for r in db[REVIEWS].find({"product_id": {"$in": ids}}, {"product_id": 1, "review_rating": 1}):
        ratings[r["product_id"]].append(r.get("review_rating"))
    return {pid: _build_detail(p, offers_by_product.get(pid, []), groups, ratings.get(pid, [])) for pid, p in products.items()}


def product_detail(db: Database, product_id: str) -> dict | None:
    return _details(db, [product_id]).get(product_id)


def _quality_labels(p: dict, rows: list[dict], verified: int, unknown_tz: int, synthetic: bool) -> list[dict]:
    codes = []
    if synthetic:
        codes.append("synthetic_dataset")
    if unknown_tz:
        codes.append("timezone_unknown")
    if any(r["current_observation"] and not r["shipping_known"] for r in rows):
        codes.append("shipping_unknown")
    if any("stock_availability_contradiction" in r["flags"] for r in rows):
        codes.append("availability_contradiction")
    if not (p.get("brand") or p.get("size") or p.get("colour")):
        codes.append("missing_product_metadata")
    if verified:
        codes.append("verified_history")
    return [{"code": c, "label": QUALITY_LABELS[c][0], "description": QUALITY_LABELS[c][1]} for c in codes]


def _build_detail(p: dict, offers: list[dict], groups: dict, ratings: list) -> dict:
    rows, verified, unknown_tz, verified_times = [], 0, 0, []
    for off in offers:
        group = groups.get(off["_id"], [])
        verified += sum(1 for g in group if g.get("history_eligible"))
        verified_times += [g["observed_at"] for g in group if g.get("history_eligible") and g.get("observed_at")]
        unknown_tz += sum(1 for g in group if g.get("timestamp_quality") == "timezone_unknown")
        cur, basis = select_current(group)
        v = offer_view(cur, basis)
        rows.append(
            {
                "listing_id": off["_id"],
                "marketplace": off.get("marketplace"),
                "seller_id": off.get("seller_id"),
                "seller_name": off.get("seller_name"),
                "product_url": _safe_url(off.get("product_url")),
                "observation_count": len(group),
                "current_observation": None
                if cur is None
                else {
                    "source_timestamp": cur.get("source_timestamp"),
                    "timestamp_quality": cur.get("timestamp_quality"),
                    "observed_at": _iso(cur.get("observed_at")),
                    "source_last_updated": cur.get("source_last_updated"),
                    "basis": basis,
                },
                **v,
                "condition": v["condition"] or off.get("condition"),
                "synthetic": off.get("synthetic"),
                "source_label": off.get("source_label"),
                "is_lowest_base": False,
                "is_lowest_delivered": False,
            }
        )

    priced_currencies = sorted({r["currency"] for r in rows if r["price_minor"] is not None})
    excluded = []
    for r in rows:
        if r["purchasable"]:
            continue
        if r["price_minor"] is None:
            why = "No current price"
        elif "stock_availability_contradiction" in [w["code"] for w in r["warnings"]]:
            why = "Availability and reported stock quantity disagree"
        elif r["availability_class"] == "out_of_stock":
            why = "Out of stock"
        else:
            why = "Availability not stated"
        excluded.append({"listing_id": r["listing_id"], "marketplace": r["marketplace"], "reason": why})
    unknown_shipping = sum(1 for r in rows if r["current_observation"] and not r["shipping_known"])
    notes = ["Lowest prices consider listings that are in stock or limited stock, with a current price and no stock warning."]
    lowest_base = lowest_delivered = None
    currency = priced_currencies[0] if len(priced_currencies) == 1 else None
    if len(priced_currencies) > 1:
        notes = [f"Listings use different currencies ({', '.join(priced_currencies)}); prices aren't compared across currencies."]
    else:
        purch = [r for r in rows if r["purchasable"]]
        if purch:
            lowest_base = min(r["price_minor"] for r in purch)
            totals = [r["total_minor"] for r in purch if r["total_minor"] is not None]
            lowest_delivered = min(totals) if totals else None
            for r in purch:
                r["is_lowest_base"] = r["price_minor"] == lowest_base
                r["is_lowest_delivered"] = lowest_delivered is not None and r["total_minor"] == lowest_delivered
        else:
            notes.append("No listing currently qualifies.")
        if unknown_shipping:
            notes.append(
                f"{unknown_shipping} listing(s) have unknown shipping, so the lowest delivered price covers only listings with known shipping."
            )

    valid = [x for x in ratings if isinstance(x, int) and 1 <= x <= 5]
    avg = _round2(Decimal(sum(valid)) / Decimal(len(valid))) if valid else None
    synthetic = bool(p.get("synthetic")) and all(r.get("synthetic") for r in rows)
    availability = {k: 0 for k in AVAILABILITY_LABELS}
    for r in rows:
        availability[r["availability_class"]] += 1
    availability["contradictions"] = sum(1 for r in rows if "stock_availability_contradiction" in r["flags"])

    return {
        "pricing": lowest_designations(rows),
        "availability_summary": availability,
        "quality_labels": _quality_labels(p, rows, verified, unknown_tz, synthetic),
        "product": {
            "product_id": p["_id"],
            "name": p.get("name"),
            "category": p.get("category"),
            "category_label": CATEGORY_LABELS.get(p.get("category"), p.get("category")),
            "source_category": p.get("source_category"),
            "brand": p.get("brand"),
            "size": p.get("size"),
            "colour": p.get("colour"),
            "image": {"kind": (p.get("image") or {}).get("kind", "none")},
            "synthetic": p.get("synthetic"),
            "source_label": p.get("source_label"),
            "source_type": p.get("source_type"),
            "offer_count": len(rows),
            "marketplaces": sorted({r["marketplace"] for r in rows}),
        },
        "offers": rows,
        "comparison": {
            "currency": currency,
            "lowest_base_price_minor": lowest_base,
            "lowest_delivered_price_minor": lowest_delivered,
            "offers_with_unknown_shipping": unknown_shipping,
            "excluded": excluded,
            "note": " ".join(notes),
        },
        "reviews_summary": {
            "count": len(ratings),
            "rated_count": len(valid),
            "average_review_rating": avg,
            "distribution": {str(k): valid.count(k) for k in range(1, 6)},
            "formula": REVIEW_FORMULA,
        },
        "price_history": {
            "status": "unavailable" if verified == 0 else "available",
            "reason": HISTORY_UNAVAILABLE if verified == 0 else HISTORY_NOT_BUILT,
            "verified_observation_count": verified,
            "timezone_unknown_observation_count": unknown_tz,
            "first_verified_at": _iso(min(verified_times)) if verified_times else None,
            "last_verified_at": _iso(max(verified_times)) if verified_times else None,
        },
        "provenance": {
            "synthetic": synthetic,
            "source_labels": sorted({x for x in [p.get("source_label")] + [r.get("source_label") for r in rows] if x}),
            "source_types": sorted({x for x in [p.get("source_type")] if x}),
        },
    }


# ---------- multi-product comparison ----------
MAX_COMPARE = 4


def _range(values: list, **extra) -> dict | None:
    vals = [v for v in values if v is not None]
    return {"min": min(vals), "max": max(vals), **extra} if vals else None


def compare_products(db: Database, product_ids: list[str]) -> dict:
    """Side-by-side summaries in the requested order. Products are matched only by stored product ID."""
    details = _details(db, product_ids)
    products, missing = [], []
    for pid in product_ids:
        d = details.get(pid)
        if d is None:
            missing.append(pid)
            continue
        offers = d["offers"]
        cur = d["pricing"]["currency"]
        products.append(
            {
                **{k: d["product"][k] for k in ("product_id", "name", "category", "category_label", "source_category", "image", "synthetic", "source_label")},
                "marketplaces": d["product"]["marketplaces"],
                "offer_count": len(offers),
                "available_offer_count": sum(1 for o in offers if o["purchasable"]),
                "availability_summary": d["availability_summary"],
                "pricing": d["pricing"],
                "reference_price_range": _range([o["reference_price_minor"] for o in offers], currency=cur) if cur else None,
                "advertised_discount_range": _range([o["discount"]["advertised_percent"] for o in offers]),
                "calculated_reduction_range": _range([o["discount"]["calculated_percent"] for o in offers]),
                "discount_differences": sum(1 for o in offers if o["discount"]["material"]),
                "product_rating_range": _range([o["product_rating"] for o in offers]),
                "seller_rating_range": _range([o["seller_rating"] for o in offers]),
                "reviews_summary": {k: d["reviews_summary"][k] for k in ("count", "rated_count", "average_review_rating")},
                "conditions": sorted({o["condition"] for o in offers if o["condition"]}),
                "quality_labels": d["quality_labels"],
                "price_history": {"status": d["price_history"]["status"], "reason": d["price_history"]["reason"]},
            }
        )

    warnings = []
    if len(products) > 1:
        cats = sorted({p["category_label"] for p in products})
        if len(cats) > 1:
            warnings.append(f"These products are in different categories ({', '.join(cats)}).")
        subs = sorted({p["source_category"] for p in products if p["source_category"]})
        if len(subs) > 1:
            warnings.append(f"These products are in different sub-categories ({', '.join(subs)}), so they may not be like-for-like.")
        currencies = sorted({p["pricing"]["currency"] for p in products if p["pricing"]["currency"]})
        if len(currencies) > 1:
            warnings.append(f"Prices are in different currencies ({', '.join(currencies)}) and aren't compared.")
        conditions = sorted({c for p in products for c in p["conditions"]})
        if len(conditions) > 1:
            warnings.append(f"Listings have different conditions ({', '.join(conditions)}).")
    return {"products": products, "missing": missing, "comparability_warnings": warnings}


def product_reviews(db: Database, product_id: str, page: int, page_size: int) -> dict | None:
    if not db[PRODUCTS].find_one({"_id": product_id}, {"_id": 1}):
        return None
    markets = {o["_id"]: o.get("marketplace") for o in db[OFFERS].find({"product_id": product_id}, {"marketplace": 1})}
    q = {"product_id": product_id}
    total = db[REVIEWS].count_documents(q)
    docs = list(db[REVIEWS].find(q).sort([("listing_id", 1), ("_id", 1)]).skip((page - 1) * page_size).limit(page_size))
    obs = {
        o["_id"]: o
        for o in db[OBSERVATIONS].find(
            {"_id": {"$in": [d.get("observation_id") for d in docs]}}, {"source_timestamp": 1, "timestamp_quality": 1}
        )
    }
    items = []
    for d in docs:
        ob = obs.get(d.get("observation_id"), {})
        items.append(
            {
                "listing_id": d.get("listing_id"),
                "marketplace": markets.get(d.get("listing_id")),
                "review_rating": d.get("review_rating"),
                "text": d.get("text"),
                "review_source": d.get("review_source"),
                "reviewer_name": d.get("reviewer_name"),
                "review_date": d.get("review_date"),
                "synthetic": d.get("synthetic"),
                "source_label": d.get("source_label"),
                "observation_source_timestamp": ob.get("source_timestamp"),
                "observation_timestamp_quality": ob.get("timestamp_quality"),
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": items}
