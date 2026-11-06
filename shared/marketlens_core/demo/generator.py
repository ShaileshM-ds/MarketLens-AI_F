"""Synthetic Demo generator (SCOPE §5).

- Deterministic: a fixed seed and a fixed end date give byte-identical exports.
- Demo database only: refuses any database whose name has no 'demo' segment.
- Every record is synthetic, with fictional brands and sellers. The rows go through the normal import
  pipeline with the strict UTC history rule, so they get the same validation, IDs and provenance as real imports.
- Planted scenarios are written to a SEPARATE answer key file (answer_key.json). It is never stored in a
  database, and analytics code never reads it.
"""

import csv
import hashlib
import io
import json
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pymongo import ReturnDocument
from pymongo.database import Database

from ..db import INGESTION_RUNS, JOBS, MODE_COLLECTIONS, PRODUCTS, ensure_mode_indexes
from ..importing.config import TARGETS, ImportConfig
from ..importing.engine import apply, evaluate
from ..importing.parsing import ParsedFile, ParsedRow
from ..importing.rows import RowContext

DEFAULT_SEED = 20261031
DEFAULT_END = date(2026, 10, 31)
DAYS = 184
VERSION = 1
GENERATOR = "MarketLens demo generator"
DATASET_FILE = "demo_dataset.csv"
KEY_FILE = "answer_key.json"

COLUMNS = [
    "product_id", "product_name", "brand", "size", "colour", "storage", "category", "listing_id", "seller_id", "seller_name",
    "marketplace", "timestamp", "last_updated", "price", "original_price", "currency", "shipping_cost", "discount",
    "coupon_discount", "payment_offer", "availability", "stock_quantity", "product_condition", "delivery_information",
    "urgency_message", "seller_rating", "product_rating", "seller_location", "source", "source_type",
    "review_id", "review", "rating", "review_source", "review_date",
]
# (launch slug, sub-category, noun, base rupees, attribute kind)
CATALOG = [
    ("mens-clothing", "T-Shirts", "Cotton Tee", 899, "size"),
    ("womens-clothing", "Kurtas", "Printed Kurta", 1299, "size"),
    ("mobile-phones", "Smartphones", "5G Phone", 18999, "storage"),
    ("wearables", "Smartwatches", "Fitness Watch", 3499, "colour"),
    ("home-appliances", "Air Fryers", "Air Fryer", 5999, "colour"),
    ("computer-accessories", "Keyboards", "Wireless Keyboard", 1799, "colour"),
    ("cameras", "Action Cameras", "Action Camera", 12999, "colour"),
    ("smart-home", "Smart Plugs", "Smart Plug", 1199, "colour"),
]
BRANDS = ["Zephyra", "Kovalt", "Nimbra", "Orvane", "Tessaro", "Quillon", "Brivo", "Lumetra", "Varnik", "Solvane", "Mirelle", "Trevo"]
COLOURS = ["Graphite", "Sky Blue", "Olive", "Ivory", "Crimson"]
SIZES = ["S", "M", "L", "XL"]
STORAGE = ["128 GB", "256 GB"]
CITIES = ["Pune, Maharashtra", "Jaipur, Rajasthan", "Kochi, Kerala", "Indore, Madhya Pradesh"]
OPENERS = ["Fictional sample:", "Synthetic sample:", "Made-up test review:"]
LIKES = ["arrived on time", "works as described", "good value for the price", "packaging was neat", "easy to set up"]
DISLIKES = ["the box was dented", "instructions were thin", "colour is slightly different", "took a day longer than shown"]
URGENCY = "Only a few left at this price! (synthetic example)"

# Scenario assignments by product index (0-based); 40 products, 5 per category.
SCENARIOS = {
    0: "genuine_discount", 1: "inflated_reference", 4: "repeated_urgency", 5: "shipping_offset", 9: "seller_switch",
    6: "mixed_event_outcomes", 7: "stable_prices", 8: "sparse_missing_days", 10: "insufficient_history",
}
MARKET_WIDE_CATEGORY = "computer-accessories"
MULTI_SELLER = {2, 9}  # two Amazon sellers
MULTI_PER_DAY = {3, 11}  # three observations a day
NO_REVIEWS = {13, 14, 15}
OUT_OF_STOCK = 16  # one listing out of stock for a stretch (stock 0, consistent)


class DemoError(Exception):
    pass


def _guard(db: Database) -> None:
    if "demo" not in db.name.split("_"):
        raise DemoError(f"Refusing to write to '{db.name}': the demo generator only writes to the Demo database.")


def _r9(x: float) -> int:
    """Rupees ending in 9, never below 49."""
    return max(49, int(round(x / 10.0)) * 10 - 1)


class _Builder:
    def __init__(self, seed: int, end: date):
        self.rng = random.Random(seed)
        self.seed = seed
        self.end = end
        self.days = [end - timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
        self.rows: list[dict] = []
        self.key: dict = {"generator": GENERATOR, "version": VERSION, "seed": seed, "end_date": end.isoformat(), "days": DAYS, "scenarios": []}

    def scenario(self, typ: str, pids: list[str], lids: list[str], start: date | None, end: date | None, **expected):
        self.key["scenarios"].append({
            "type": typ, "product_ids": pids, "listing_ids": lids,
            "window": {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
            "expected": expected,
        })

    def build(self) -> None:
        rng, D = self.rng, DAYS
        source = f"{GENERATOR} (seed {self.seed})"
        products = []
        for i in range(40):
            slug, sub, noun, base, kind = CATALOG[i // 5]
            pid = f"DEMO-P-{i + 1:03d}"
            brand = BRANDS[(i * 7) % len(BRANDS)]
            attrs = {"size": "", "colour": "", "storage": ""}
            if kind == "size":
                attrs["size"] = SIZES[i % len(SIZES)]
                attrs["colour"] = COLOURS[i % len(COLOURS)]
            elif kind == "storage":
                attrs["storage"] = STORAGE[i % len(STORAGE)]
                attrs["colour"] = COLOURS[i % len(COLOURS)]
            else:
                attrs["colour"] = COLOURS[i % len(COLOURS)]
            name = f"{brand} {noun} " + " ".join(v for v in (attrs["size"] and f"Size {attrs['size']}", attrs["storage"], attrs["colour"]) if v)
            markets = ["Amazon", "Flipkart", "Myntra"] if "clothing" in slug else ["Amazon", "Flipkart"]
            listings = []
            for m in markets:
                sellers = 2 if (m == "Amazon" and i in MULTI_SELLER) else 1
                for s in range(sellers):
                    sid = f"DEMO-S-{m[:3].upper()}-{(i + s) % 6 + 1}"
                    listings.append({
                        "listing_id": f"DEMO-L-{i + 1:03d}-{m[:3].upper()}{s + 1}",
                        "marketplace": m, "seller_id": sid,
                        "seller_name": f"Demo Seller {m} {(i + s) % 6 + 1} (fictional)",
                        "factor": 1 + rng.uniform(-0.03, 0.03) + (0.05 if s else 0.0),
                        "seller_rating": round(rng.uniform(3.8, 4.7), 1), "product_rating": round(rng.uniform(3.5, 4.8), 1),
                        "city": CITIES[(i + s) % len(CITIES)],
                    })
            products.append({"i": i, "pid": pid, "name": name, "brand": brand, "slug": slug, "sub": sub, "base": base * (1 + (i % 5) * 0.07), **attrs, "listings": listings})

        mw_start = D - 60
        for p in products:
            i, scen = p["i"], SCENARIOS.get(p["i"])
            days = self.days[-10:] if scen == "insufficient_history" else self.days
            offset = D - len(days)
            skip = {d for d in range(D) if scen == "sparse_missing_days" and self.rng.random() < 0.4}
            level = 1.0
            mixed = [(40, "returned"), (80, "stayed_low"), (120, "returned"), (160, "stayed_low")]
            for k, day in enumerate(days):
                d = k + offset
                if scen != "stable_prices":
                    level = min(1.06, max(0.94, level * (1 + self.rng.uniform(-0.008, 0.008))))
                if d in skip:
                    continue
                for li, lst in enumerate(p["listings"]):
                    f = level * lst["factor"]
                    ref_mult = 1.3
                    ship_extra = 0
                    urgency = ""
                    if scen == "genuine_discount" and d >= D - 20:
                        f *= 0.8
                    if scen == "inflated_reference" and d >= D - 30:
                        ref_mult *= 1.5
                    if scen == "repeated_urgency" and d >= D - 60:
                        urgency = URGENCY
                    if scen == "shipping_offset" and d >= D - 30:
                        f *= 0.9
                        ship_extra = 0.1
                    if scen == "seller_switch" and lst["marketplace"] == "Amazon":
                        first = li == 0
                        cheaper = first if d < D - 45 else not first
                        f = level * (0.95 if cheaper else 1.0)
                    if scen == "mixed_event_outcomes":
                        for start, outcome in mixed:
                            if start <= d < start + 7 or (outcome == "stayed_low" and start + 7 <= d < start + 21):
                                f *= 0.85
                    if p["slug"] == MARKET_WIDE_CATEGORY and d >= mw_start:
                        f *= 1.08
                    price = _r9(p["base"] * f)
                    ref = _r9(p["base"] * ref_mult)
                    ref = max(ref, price)
                    if lst["marketplace"] == "Myntra":
                        ship = 0
                    elif lst["marketplace"] == "Amazon":
                        ship = 0 if price >= 499 else 40
                    else:
                        ship = 40
                    ship += int(round(price * ship_extra))
                    avail, stock = "In Stock", 10 + (d * 7 + li * 13 + i) % 51
                    if (d + i + li) % 47 == 0:
                        avail, stock = "Limited Stock", 1 + (d % 4)
                    if i == OUT_OF_STOCK and li == 0 and 100 <= d < 106:
                        avail, stock = "Out of Stock", 0
                    times = (8, 14, 20) if (i in MULTI_PER_DAY and li == 0) else (10,)
                    for t, hour in enumerate(times):
                        ts = f"{day.isoformat()}T{hour:02d}:00:00Z"
                        tprice = price if t == 0 else _r9(price * (1 + 0.01 * (t - 1)))
                        tprice = min(tprice, ref)
                        self.rows.append({
                            "product_id": p["pid"], "product_name": p["name"], "brand": p["brand"], "size": p["size"],
                            "colour": p["colour"], "storage": p["storage"], "category": p["sub"],
                            "listing_id": lst["listing_id"], "seller_id": lst["seller_id"], "seller_name": lst["seller_name"],
                            "marketplace": lst["marketplace"], "timestamp": ts, "last_updated": ts,
                            "price": str(tprice), "original_price": str(ref), "currency": "INR", "shipping_cost": str(ship),
                            "discount": f"{(ref - tprice) / ref * 100:.2f}",
                            "coupon_discount": "100" if day.weekday() == 5 else "0",
                            "payment_offer": "Eligible card offer: 5% up to ₹200 (synthetic)" if day.day % 10 == 0 else "No payment offer",
                            "availability": avail, "stock_quantity": str(stock), "product_condition": "New",
                            "delivery_information": f"Delivery in {2 + (d + li) % 4}-{4 + (d + li) % 4} days",
                            "urgency_message": urgency, "seller_rating": str(lst["seller_rating"]),
                            "product_rating": str(lst["product_rating"]), "seller_location": lst["city"],
                            "source": source, "source_type": "Synthetic",
                            "review_id": "", "review": "", "rating": "", "review_source": "", "review_date": "",
                        })

            # Reviews: attached to observation rows of the first listing, each with its own ID and date.
            if i not in NO_REVIEWS:
                n = 3 + (i * 5) % 13
                own = [r for r in self.rows if r["listing_id"] == p["listings"][0]["listing_id"] and r["timestamp"].endswith("T10:00:00Z") or
                       (r["listing_id"] == p["listings"][0]["listing_id"] and i in MULTI_PER_DAY and r["timestamp"].endswith("T08:00:00Z"))]
                step = max(1, len(own) // n)
                for k in range(min(n, len(own))):
                    row = own[k * step]
                    rating = self.rng.choice([2, 3, 4, 4, 5, 5])
                    good = self.rng.choice(LIKES)
                    text = f"{self.rng.choice(OPENERS)} {good}." if rating >= 4 else f"{self.rng.choice(OPENERS)} {good}, but {self.rng.choice(DISLIKES)}."
                    row.update({"review_id": f"DEMO-R-{i + 1:03d}-{k + 1:02d}", "review": text, "rating": str(rating),
                                "review_source": "Synthetic sample review (MarketLens demo generator)", "review_date": row["timestamp"][:10]})

            lids = [l["listing_id"] for l in p["listings"]]
            if scen == "genuine_discount":
                self.scenario(scen, [p["pid"]], lids, self.days[D - 20], self.end, price_change_pct=-20, reference_changed=False,
                              note="Real savings of about 20% against the prior median; the advertised discount also rises.")
            elif scen == "inflated_reference":
                self.scenario(scen, [p["pid"]], lids, self.days[D - 30], self.end, reference_change_pct=50, price_change_pct=0,
                              note="Advertised discount jumps while the price doesn't move: real savings about 0%.")
            elif scen == "repeated_urgency":
                self.scenario(scen, [p["pid"]], lids, self.days[D - 60], self.end, urgency_days=60, low_stock_days=0,
                              note="Urgency message every day while stock stays normal.")
            elif scen == "shipping_offset":
                self.scenario(scen, [p["pid"]], lids, self.days[D - 30], self.end, base_change_pct=-10, shipping_added_pct_of_base=10,
                              note="Base price drops about 10% but added shipping keeps the delivered price about the same.")
            elif scen == "seller_switch":
                amz = [l for l in p["listings"] if l["marketplace"] == "Amazon"]
                self.scenario(scen, [p["pid"]], [l["listing_id"] for l in amz], self.days[D - 45], self.end,
                              cheapest_seller_before=amz[0]["seller_id"], cheapest_seller_after=amz[1]["seller_id"])
            elif scen == "mixed_event_outcomes":
                self.scenario(scen, [p["pid"]], lids, self.days[40], self.days[180], events=[
                    {"start": self.days[s].isoformat(), "end": self.days[s + 6].isoformat(), "price_change_pct": -15, "outcome_after_7_days": o}
                    for s, o in mixed])
            elif scen == "stable_prices":
                self.scenario(scen, [p["pid"]], lids, self.days[0], self.end, price_change_pct=0, note="No movement apart from listing offsets.")
            elif scen == "sparse_missing_days":
                self.scenario(scen, [p["pid"]], lids, self.days[0], self.end, missing_days=len(skip), observed_days=DAYS - len(skip))
            elif scen == "insufficient_history":
                self.scenario(scen, [p["pid"]], lids, self.days[-10], self.end, distinct_days=10,
                              note="Fewer than 14 days: history-based scores must say 'unavailable'.")

        mw = [p for p in products if p["slug"] == MARKET_WIDE_CATEGORY]
        self.scenario("market_wide_movement", [p["pid"] for p in mw], [l["listing_id"] for p in mw for l in p["listings"]],
                      self.days[mw_start], self.end, price_change_pct=8, note="Every product in the category moves together.")
        self.key["products_without_reviews"] = [f"DEMO-P-{i + 1:03d}" for i in sorted(NO_REVIEWS)]
        self.key["multi_seller_products"] = [f"DEMO-P-{i + 1:03d}" for i in sorted(MULTI_SELLER)]
        self.key["multi_observation_per_day_products"] = [f"DEMO-P-{i + 1:03d}" for i in sorted(MULTI_PER_DAY)]
        self.key["out_of_stock_window"] = {"product_id": f"DEMO-P-{OUT_OF_STOCK + 1:03d}", "start": self.days[100].isoformat(), "end": self.days[105].isoformat()}
        self.rows.sort(key=lambda r: (r["timestamp"], r["listing_id"]))
        self.categories = {c[1]: c[0] for c in CATALOG}


def _csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def generate_demo(db: Database, *, export_dir: Path, now: datetime, seed: int = DEFAULT_SEED, end: date = DEFAULT_END) -> dict:
    _guard(db)
    ensure_mode_indexes(db)
    if db[PRODUCTS].count_documents({}):
        raise DemoError("Demo data already exists. Reset it first.")
    b = _Builder(seed, end)
    b.build()
    data = _csv(b.rows)
    key = json.dumps(b.key, indent=2, sort_keys=True).encode("utf-8")
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / DATASET_FILE).write_bytes(data)
    (export_dir / KEY_FILE).write_bytes(key)

    run_id = uuid.uuid4().hex
    config = ImportConfig(field_map={c: c for c in COLUMNS if c in TARGETS}, category_map=b.categories, timestamp_policy="require_utc")
    parsed = ParsedFile("csv", COLUMNS, [ParsedRow(n, row) for n, row in enumerate(b.rows, start=1)])
    ctx = RowContext(run_id=run_id, source_file_id=f"demo-seed-{seed}", source_filename=DATASET_FILE, now=now, timestamp_policy="require_utc")
    summary = apply(db, evaluate(db, parsed, config, ctx), ctx)
    db[INGESTION_RUNS].insert_one({
        "_id": run_id, "type": "demo_generator", "mode": "demo", "status": "completed",
        "file": {"filename": DATASET_FILE, "format": "csv", "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
        "generator": {"name": GENERATOR, "version": VERSION, "seed": seed, "end_date": end.isoformat(),
                      "answer_key_file": KEY_FILE, "answer_key_sha256": hashlib.sha256(key).hexdigest()},
        "summary": summary, "created_by": "demo generator", "created_at": now, "finished_at": now,
    })
    return {"run_id": run_id, "rows": len(b.rows), "rejected": summary["rejected"], "created": summary["created"],
            "export": {"dataset": DATASET_FILE, "answer_key": KEY_FILE}}


def reset_demo(db: Database) -> dict:
    """Empties every Demo collection (data and Demo-workspace watchlists/alerts). Accounts live elsewhere."""
    _guard(db)
    return {c: db[c].delete_many({}).deleted_count for c in sorted(set(db.list_collection_names()) | set(MODE_COLLECTIONS)) if c != JOBS}


def status(db: Database) -> dict:
    run = db[INGESTION_RUNS].find_one({"type": "demo_generator"}, sort=[("created_at", -1)])
    jobs = list(db[JOBS].find({"type": {"$in": ["demo_generate", "demo_reset"]}}, {"type": 1, "status": 1, "error": 1, "created_at": 1}).sort("created_at", -1).limit(5))
    return {
        "database": db.name,
        "products": db[PRODUCTS].count_documents({}),
        "observations": db["observations"].count_documents({}),
        "reviews": db["reviews"].count_documents({}),
        "last_run": None if not run else {"id": run["_id"], "created_at": run["created_at"], "seed": run["generator"]["seed"],
                                          "end_date": run["generator"]["end_date"], "summary": run["summary"],
                                          "answer_key_sha256": run["generator"]["answer_key_sha256"]},
        "jobs": [{"id": j["_id"], "type": j["type"], "status": j["status"], "error": j.get("error"), "created_at": j["created_at"]} for j in jobs],
        "export_location": "data/demo-export/",
    }


def queue_job(db: Database, kind: str, user: str, now: datetime) -> dict:
    _guard(db)
    if kind == "demo_generate" and db[PRODUCTS].count_documents({}):
        raise DemoError("Demo data already exists. Reset it first.")
    job = {"_id": uuid.uuid4().hex, "type": kind, "status": "queued", "created_by": user, "created_at": now, "attempts": 0}
    db[JOBS].insert_one(job)
    return {"id": job["_id"], "type": kind, "status": "queued"}


def process_next_demo_job(db: Database, *, export_dir: Path, now_fn) -> dict | None:
    job = db[JOBS].find_one_and_update(
        {"type": {"$in": ["demo_generate", "demo_reset"]}, "status": "queued"},
        {"$set": {"status": "running", "started_at": now_fn()}, "$inc": {"attempts": 1}},
        sort=[("created_at", 1)], return_document=ReturnDocument.AFTER,
    )
    if not job:
        return None
    try:
        result = generate_demo(db, export_dir=export_dir, now=now_fn()) if job["type"] == "demo_generate" else reset_demo(db)
        db[JOBS].update_one({"_id": job["_id"]}, {"$set": {"status": "completed", "finished_at": now_fn(), "result": json.loads(json.dumps(result, default=str))}})
    except DemoError as exc:
        db[JOBS].update_one({"_id": job["_id"]}, {"$set": {"status": "failed", "finished_at": now_fn(), "error": str(exc)}})
    return job
