"""Evaluate parsed rows against stored state, then apply (insert-only for observations).

The same evaluate() drives the wizard's preview and the real import, so the
preview counts match what the import does (unless other data arrives between).
"""

from collections import Counter
from dataclasses import dataclass, field

from pymongo import UpdateOne
from pymongo.database import Database
from pymongo.errors import BulkWriteError

from ..db import OBSERVATIONS, OFFERS, PRODUCTS, REJECTED_RECORDS, REVIEWS
from ..explorer import rebuild_product_summaries
from .config import ImportConfig
from .parsing import ParsedFile
from .rows import Issue, RowContext, RowResult, map_row

PREVIEW_ROWS = 20
EXAMPLE_ROWS = 50


@dataclass
class Outcome:
    result: RowResult
    status: str  # accepted | duplicate | rejected
    review_status: str | None = None  # new | duplicate | None


@dataclass
class Evaluation:
    outcomes: list[Outcome] = field(default_factory=list)
    new_product_ids: set[str] = field(default_factory=set)
    new_listing_ids: set[str] = field(default_factory=set)


def _find_in(coll, ids, projection):
    ids = list(ids)
    out = {}
    for i in range(0, len(ids), 1000):
        for doc in coll.find({"_id": {"$in": ids[i : i + 1000]}}, projection):
            out[doc["_id"]] = doc
    return out


def evaluate(db: Database, parsed: ParsedFile, config: ImportConfig, ctx: RowContext) -> Evaluation:
    results = [map_row(r, config, ctx) for r in parsed.rows]
    ok = [r for r in results if r.ok]

    stored_offers = _find_in(db[OFFERS], {r.offer["_id"] for r in ok}, {"product_id": 1, "seller_id": 1})
    stored_products = _find_in(db[PRODUCTS], {r.product["_id"] for r in ok}, {"name": 1, "source_category": 1})
    stored_obs = _find_in(db[OBSERVATIONS], {r.observation["_id"] for r in ok}, {"content_hash": 1})
    stored_reviews = _find_in(db[REVIEWS], {r.review["_id"] for r in ok if r.review}, {"_id": 1})

    ev = Evaluation()
    seen_offers: dict[str, dict] = {}
    seen_products: dict[str, dict] = {}
    seen_obs: dict[str, str] = {}
    seen_reviews: set[str] = set()

    for r in results:
        if not r.ok:
            ev.outcomes.append(Outcome(r, "rejected"))
            continue
        lid, pid = r.offer["_id"], r.product["_id"]
        known = stored_offers.get(lid) or seen_offers.get(lid)
        if known and (known["product_id"], known["seller_id"]) != (pid, r.offer["seller_id"]):
            r.reasons.append(
                Issue(
                    "listing_identity_conflict",
                    f"listing {lid} already belongs to product {known['product_id']} and seller "
                    f"{known['seller_id']}; a listing's product and seller can't change",
                )
            )
            ev.outcomes.append(Outcome(r, "rejected"))
            continue

        oid, h = r.observation["_id"], r.observation["content_hash"]
        prior = stored_obs[oid]["content_hash"] if oid in stored_obs else seen_obs.get(oid)
        if prior is not None and prior != h:
            r.reasons.append(
                Issue(
                    "immutable_conflict",
                    f"an observation for listing {lid} at source time {r.observation['source_timestamp']} already "
                    "exists with different values; stored observations are immutable and were not changed",
                )
            )
            ev.outcomes.append(Outcome(r, "rejected"))
            continue

        stored_p = stored_products.get(pid) or seen_products.get(pid)
        if stored_p:
            if stored_p["name"] != r.product["name"]:
                r.warnings.append(
                    Issue("product_name_mismatch", f"Product name differs from the stored name '{stored_p['name']}'; the stored name was kept")
                )
            if stored_p["source_category"] != r.product["source_category"]:
                r.warnings.append(
                    Issue("product_category_mismatch", f"Category differs from the stored '{stored_p['source_category']}'; the stored category was kept")
                )
        else:
            ev.new_product_ids.add(pid)
            seen_products[pid] = r.product
        if not known:
            ev.new_listing_ids.add(lid)
            seen_offers[lid] = r.offer

        status = "duplicate" if prior is not None else "accepted"
        seen_obs[oid] = h
        review_status = None
        if r.review:
            rid = r.review["_id"]
            review_status = "duplicate" if (rid in stored_reviews or rid in seen_reviews) else "new"
            seen_reviews.add(rid)
        ev.outcomes.append(Outcome(r, status, review_status))
    return ev


def counts(ev: Evaluation) -> dict:
    c = Counter(o.status for o in ev.outcomes)
    kept = [o for o in ev.outcomes if o.status != "rejected"]
    warn_types = Counter(w.code for o in kept for w in o.result.warnings)
    reject_types = Counter(o.result.reasons[0].code for o in ev.outcomes if o.status == "rejected")
    return {
        "rows_total": len(ev.outcomes),
        "accepted": c["accepted"],
        "duplicate": c["duplicate"],
        "rejected": c["rejected"],
        "warning_rows": sum(1 for o in kept if o.result.warnings),
        "warning_count": sum(warn_types.values()),
        "warnings_by_type": dict(warn_types),
        "rejected_by_reason": dict(reject_types),
        "reviews_new": sum(1 for o in ev.outcomes if o.review_status == "new"),
        "reviews_duplicate": sum(1 for o in ev.outcomes if o.review_status == "duplicate"),
        "products_new": len(ev.new_product_ids),
        "listings_new": len(ev.new_listing_ids),
    }


def preview_row(o: Outcome) -> dict:
    r = o.result
    obs = r.observation or {}
    return {
        "row_number": r.row_number,
        "status": o.status,
        "product_id": (r.product or {}).get("product_id") or r.raw.get("product_id"),
        "listing_id": (r.offer or {}).get("listing_id") or r.raw.get("listing_id"),
        "marketplace": (r.offer or {}).get("marketplace"),
        "category": (r.product or {}).get("category"),
        "source_category": (r.product or {}).get("source_category"),
        "source_timestamp": obs.get("source_timestamp"),
        "timestamp_quality": obs.get("timestamp_quality"),
        "currency": obs.get("currency"),
        "price_minor": obs.get("price_minor"),
        "reference_price_minor": obs.get("reference_price_minor"),
        "shipping_minor": obs.get("shipping_minor"),
        "shipping_known": obs.get("shipping_known"),
        "availability": obs.get("availability"),
        "stock_quantity": obs.get("stock_quantity"),
        "synthetic": obs.get("synthetic"),
        "review_rating": (r.review or {}).get("review_rating"),
        "reasons": [i.message for i in r.reasons],
        "warnings": [i.message for i in r.warnings],
    }


def describe(ev: Evaluation) -> dict:
    """Stored on the run for the wizard's Preview and Validation steps."""
    rejected = [o for o in ev.outcomes if o.status == "rejected"]
    warned = [o for o in ev.outcomes if o.status != "rejected" and o.result.warnings]
    return {
        "counts": counts(ev),
        "preview_rows": [preview_row(o) for o in ev.outcomes[:PREVIEW_ROWS]],
        "rejected_examples": [preview_row(o) for o in rejected[:EXAMPLE_ROWS]],
        "warning_examples": [preview_row(o) for o in warned[:EXAMPLE_ROWS]],
    }


def apply(db: Database, ev: Evaluation, ctx: RowContext) -> dict:
    kept = [o for o in ev.outcomes if o.status != "rejected"]

    def upsert_new(coll, docs):
        ops = [UpdateOne({"_id": d["_id"]}, {"$setOnInsert": d}, upsert=True) for d in docs]
        return db[coll].bulk_write(ops, ordered=False).upserted_count if ops else 0

    products = {o.result.product["_id"]: o.result.product for o in kept if o.result.product["_id"] in ev.new_product_ids}
    offers = {o.result.offer["_id"]: o.result.offer for o in kept if o.result.offer["_id"] in ev.new_listing_ids}
    created_products = upsert_new(PRODUCTS, products.values())
    created_offers = upsert_new(OFFERS, offers.values())

    def insert_only(coll, docs) -> int:
        """Insert; an existing _id (a concurrent import) is left untouched and counted as duplicate."""
        if not docs:
            return 0
        try:
            return len(db[coll].insert_many(docs, ordered=False).inserted_ids)
        except BulkWriteError as exc:
            errors = exc.details.get("writeErrors", [])
            if any(e.get("code") != 11000 for e in errors):
                raise
            return exc.details.get("nInserted", 0)

    new_obs = [o.result.observation for o in kept if o.status == "accepted"]
    new_reviews = [o.result.review for o in kept if o.review_status == "new"]
    created_obs = insert_only(OBSERVATIONS, new_obs)
    created_reviews = insert_only(REVIEWS, new_reviews)

    rejected = [o for o in ev.outcomes if o.status == "rejected"]
    if rejected:
        db[REJECTED_RECORDS].insert_many(
            [
                {
                    "run_id": ctx.run_id,
                    "row_number": o.result.row_number,
                    "reasons": [{"code": i.code, "message": i.message} for i in o.result.reasons],
                    "raw": o.result.raw,  # complete original row, unchanged
                    "raw_source_ref": f"{ctx.source_file_id}:{ctx.source_filename}#row={o.result.row_number}",
                    "provenance": {
                        "ingestion_run_id": ctx.run_id,
                        "source_file_id": ctx.source_file_id,
                        "source_filename": ctx.source_filename,
                        "raw_source_ref": f"{ctx.source_file_id}:{ctx.source_filename}#row={o.result.row_number}",
                        "row_number": o.result.row_number,
                        "schema_version": ctx.schema_version,
                        "timestamp_policy": ctx.timestamp_policy,
                        "quarantined_at": ctx.now,
                    },
                    "created_at": ctx.now,
                }
                for o in rejected
            ]
        )

    # Keep the explorer read model current for products that gained listings or observations.
    affected = {o.result.product["_id"] for o in kept if o.status == "accepted" or o.result.offer["_id"] in ev.new_listing_ids}
    if affected:
        rebuild_product_summaries(db, affected, now=ctx.now)

    summary = counts(ev)
    raced_obs = len(new_obs) - created_obs
    summary["accepted"] -= raced_obs
    summary["duplicate"] += raced_obs
    summary["reviews_duplicate"] += len(new_reviews) - created_reviews
    summary["reviews_new"] = created_reviews
    summary["created"] = {
        "products": created_products,
        "offers": created_offers,
        "observations": created_obs,
        "reviews": created_reviews,
    }
    return summary
