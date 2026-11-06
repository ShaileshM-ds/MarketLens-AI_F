"""Shareable Demo reference pack (`data/demo-reference/`): CSV exports of the synthetic Demo database, local
artwork, schema, README and a manifest with checksums. Deterministic: rows sorted by ID, fixed formatting, and
the generated-at time is the Demo generation run's time (not the export time). Read-only on the database.
Demo databases only. Never exports accounts, sessions, watchlists, alerts, notifications or the answer key.

Run: `python -m marketlens_core.demo.reference <out_dir>` (uses MONGO_URI; reads the Demo database).
"""

import csv
import hashlib
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo.database import Database

from ..db import INGESTION_RUNS, OBSERVATIONS, OFFERS, PRODUCTS, REVIEWS
from . import artwork
from .generator import _guard

PACK_VERSION = "1"
PROV = ["ingestion_run_id", "source_file_id", "source_filename", "raw_source_ref", "row_number", "schema_version", "ingested_at"]
COMMON = ["synthetic", "source", "source_type", "source_label"]
TABLES = {
    "products.csv": (PRODUCTS, ["product_id", "name", "brand", "category", "source_category", "size", "colour", "storage", "image_path", *COMMON, *PROV]),
    "offers.csv": (OFFERS, ["listing_id", "product_id", "seller_id", "seller_name", "marketplace", "condition", "product_url", *COMMON, *PROV]),
    "observations.csv": (OBSERVATIONS, [
        "observation_id", "listing_id", "product_id", "seller_id", "marketplace", "observed_at", "timestamp_quality", "history_eligible",
        "source_timestamp", "source_last_updated", "currency", "price_minor", "reference_price_minor", "shipping_minor", "shipping_known",
        "advertised_discount_percent", "coupon_discount_minor", "payment_offer", "offers_applied_to_price", "availability", "stock_quantity",
        "urgency_message", "condition", "delivery_information", "seller_rating", "product_rating", "seller_location", "flags", "content_hash",
        *COMMON, *PROV]),
    "reviews.csv": (REVIEWS, ["review_id", "external_review_id", "product_id", "listing_id", "observation_id", "review_rating", "text",
                              "review_date", "reviewer_name", "review_source", *COMMON, *PROV]),
}
ID_COLUMN = {"observations.csv": "observation_id", "reviews.csv": "review_id"}


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):
        v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(v, (list, tuple)):
        return ";".join(str(x) for x in v)
    return str(v)


def _row(name: str, doc: dict) -> dict:
    prov = doc.get("provenance") or {}
    out = {}
    for col in TABLES[name][1]:
        if col in PROV:
            out[col] = _cell(prov.get(col))
        elif col == ID_COLUMN.get(name):
            out[col] = _cell(doc["_id"])
        elif col == "image_path":
            out[col] = f"images/{doc['_id']}.svg" if (artwork.N_PRODUCTS and doc["_id"].startswith("DEMO-P-")) else f"images/{artwork.FALLBACK}"
        else:
            out[col] = _cell(doc.get(col))
    return out


def _csv(name: str, docs) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TABLES[name][1], lineterminator="\n")
    w.writeheader()
    n = 0
    for d in docs:
        w.writerow(_row(name, d))
        n += 1
    return buf.getvalue().encode("utf-8"), n


def export_reference(db: Database, out_dir: Path) -> dict:
    _guard(db)
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "answer-key").mkdir(parents=True)
    run = db[INGESTION_RUNS].find_one({"type": "demo_generator"}, sort=[("created_at", -1), ("_id", -1)])
    if not run:
        raise ValueError("No Demo generation run found: generate Demo data first.")
    files, counts = {}, {}
    for name, (coll, _cols) in TABLES.items():
        data, n = _csv(name, db[coll].find({}, {"raw": 0}).sort("_id", 1))
        (out_dir / name).write_bytes(data)
        files[name], counts[name] = data, n
    images = artwork.write_images(out_dir / "images")
    gen = run["generator"]
    schema_version = (db[OBSERVATIONS].find_one({}, {"provenance.schema_version": 1}) or {}).get("provenance", {}).get("schema_version")
    for name, text in (("README.md", README), ("schema.md", SCHEMA), ("answer-key/README.md", ANSWER_KEY_README)):
        data = text.encode("utf-8")
        (out_dir / name).write_bytes(data)
        files[name] = data
    for img in images:
        files[f"images/{img}"] = (out_dir / "images" / img).read_bytes()
    created = run["created_at"] if run["created_at"].tzinfo else run["created_at"].replace(tzinfo=timezone.utc)
    manifest = {
        "pack": "MarketLens AI Demo reference pack", "pack_version": PACK_VERSION, "mode": "demo", "synthetic": True,
        "generator": {"name": gen.get("name"), "version": gen.get("version"), "seed": gen.get("seed"), "end_date": gen.get("end_date")},
        "generated_at": _cell(created), "generation_run_id": run["_id"], "schema_version": schema_version,
        "money": "integer minor units (paise for INR)", "image_assets": len(images),
        "excluded": "No accounts, login data, watched products, alert rules, user messages or test-only scenario labels are included.",
        "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), **({"rows": counts[name]} if name in counts else {})}
                  for name, data in sorted(files.items())},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


README = """# MarketLens AI: Demo reference pack

**Every record and image in this pack is fictional and synthetic, made for project demonstration only.**
Brands, sellers, products, prices, reviews and artwork were produced by the MarketLens demo generator. None of them describe real products, stores or people.

## What is here

| File | Contents |
|---|---|
| `products.csv` | One row per product (40) |
| `offers.csv` | One row per store listing. The application calls these "offers"; a listing is one seller selling one product on one store |
| `observations.csv` | One row per observed state of a listing at a time: price, shipping, stock and so on |
| `reviews.csv` | Synthetic sample reviews |
| `images/` | Local SVG artwork for every product, plus `fallback.svg` |
| `schema.md` | Every field, its type, units, null meaning and keys |
| `manifest.json` | Generator seed and version, row counts, file checksums and the image count |
| `answer-key/README.md` | Why the test-only answer key is not in this pack |

## Relationships

- **Product:** a product (`product_id`) is sold through one or more listings (`listing_id`).
- **Listing:** each listing belongs to exactly one seller (`seller_id`) on one store (`marketplace`).
- **Observation:** belongs to one listing. Many observations make up its price history.
- **Review:** attached to the observation row it came with.
- **Cross-store link:** `product_id` is the only link between stores. Products are never matched by title.
- **Seller IDs:** never merged by seller name.

## Money

- All amounts are integers in minor units: ₹1,380.00 is stored as `138000` (paise).
- Divide by 100 only for display, through one formatting function.
- Never store or compute money as floats.
- **Unknown values:**
  - A blank `shipping_minor` means shipping is unknown. Never treat it as free.
  - `shipping_known=false` means "Total incomplete".

## Data modes

- This pack is **Demo-only**. Load it only into a Demo database.
- It must never be imported into Imported or Live data by default, and Demo, Imported and Live must never be mixed.

## Time, identity and immutability

- **Times:**
  - `observed_at` is a UTC time (ISO 8601 ending in `Z`). Every Demo observation has `timestamp_quality=utc` and `history_eligible=true`.
  - `source_timestamp` is the timestamp exactly as supplied.
  - Historical analyses always take an explicit UTC cutoff and never read observations after it.
- **Identity:**
  - `observation_id = obs1|<listing_id>|utc:<UTC time>`.
  - Re-importing the same row produces the same ID and is a duplicate.
  - A row with the same ID but different values is rejected.
- **Immutability:** observations are only ever inserted, never updated.
- **Provenance:**
  - `synthetic=true` and `source_label` mark every record as synthetic.
  - `ingestion_run_id`, `source_file_id`, `source_filename`, `raw_source_ref`, `row_number`, `schema_version` and `ingested_at` record where each record came from.

## Answer key

The generator also writes a separate answer key listing the planted test scenarios.

- It is **test-only**: used to evaluate analytics in automated tests.
- It must never be used by application analytics.
- It is deliberately **not** in this pack. See `answer-key/README.md`.

## Integrity

`manifest.json` lists the SHA-256 checksum and row count of every file. Verify the checksums before loading.
"""

SCHEMA = """# Demo reference pack: schema

## Conventions

- **Types:**
  - Text is UTF-8.
  - Booleans are `true`/`false`.
  - Times are ISO 8601 UTC ending in `Z`.
  - Lists are joined with `;`.
- **Empty cell:** the value is unknown or not supplied. It is never zero, free or false by default.
- **Money:** columns ending in `_minor` are integers in minor units of `currency` (INR paise).

## Relationships

```
products (product_id) 1 ──< offers (listing_id; product_id, seller_id, marketplace)
offers   (listing_id) 1 ──< observations (observation_id; listing_id, product_id, seller_id)
observations (observation_id) 1 ──< reviews (review_id; observation_id, listing_id, product_id)
```

## Shared columns (every file)

| Column | Type | Meaning |
|---|---|---|
| synthetic | bool | `true`: generated demonstration data |
| source | text | Generator name and seed |
| source_type | text | `Synthetic` |
| source_label | text | Provenance label shown in the application |
| ingestion_run_id | text | The generation/import run that stored the record |
| source_file_id | text | ID of the source file of the run |
| source_filename | text | Name of the source file |
| raw_source_ref | text | `<file id>:<file name>#row=<n>`, the original row |
| row_number | int | Row in the source file |
| schema_version | text | Import schema version |
| ingested_at | time | When the record was stored (not a market observation time) |

## products.csv

Key: `product_id`.

| Column | Type | Meaning |
|---|---|---|
| product_id | text | Product ID, e.g. `DEMO-P-001`. The only cross-store link |
| name | text | Fictional product name |
| brand | text | Fictional brand |
| category | text | Launch category slug, e.g. `mobile-phones` |
| source_category | text | Original sub-category |
| size, colour, storage | text | Variant attributes; empty when they don't apply |
| image_path | text | Path inside this pack, e.g. `images/DEMO-P-001.svg` |

## offers.csv

Key: `listing_id`.

| Column | Type | Meaning |
|---|---|---|
| listing_id | text | Store listing ID (one seller, one store, one product) |
| product_id | text | → products.product_id |
| seller_id | text | Seller ID. Never merged by name |
| seller_name | text | Fictional seller name |
| marketplace | text | Amazon, Flipkart or Myntra (used as fictional store labels) |
| condition | text | Product condition, if supplied |
| product_url | text | Empty: no real store pages |

## observations.csv

Key: `observation_id`, built from listing and UTC time. Duplicates have the same ID, and stored rows are never changed.

| Column | Type | Meaning |
|---|---|---|
| observation_id | text | `obs1\\|<listing_id>\\|utc:<time>` |
| listing_id, product_id, seller_id, marketplace | text | → offers / products |
| observed_at | time | UTC observation time (history uses this) |
| timestamp_quality | text | `utc`, `offset_converted` or `timezone_unknown` |
| history_eligible | bool | `true` only for verified UTC times |
| source_timestamp, source_last_updated | text | As supplied |
| currency | text | ISO 4217, e.g. `INR` |
| price_minor | int | Listed (base) price |
| reference_price_minor | int | Seller's reference ("original"/MRP) price |
| shipping_minor | int | Shipping cost; empty = unknown, `0` = known free |
| shipping_known | bool | Whether shipping is known |
| advertised_discount_percent | number | Discount the seller displayed |
| coupon_discount_minor | int | Conditional coupon; never subtracted from prices |
| payment_offer | text | Conditional payment offer text |
| offers_applied_to_price | bool | Whether the price already includes offers |
| availability | text | As reported (In Stock, Limited Stock, Out of Stock) |
| stock_quantity | int | Reported stock; empty = unknown |
| urgency_message | text | Urgency text shown, if any |
| condition, delivery_information, seller_location | text | As supplied |
| seller_rating, product_rating | number | Per store, 0–5 |
| flags | list | Data warnings, e.g. `stock_availability_contradiction` |
| content_hash | text | Hash of the stored values, used to detect conflicting re-imports |

## reviews.csv

Key: `review_id`; `external_review_id` is the supplied ID.

| Column | Type | Meaning |
|---|---|---|
| review_id | text | `rev1\\|id:<external_review_id>` |
| external_review_id | text | Supplied review ID |
| product_id, listing_id, observation_id | text | → products / offers / observations |
| review_rating | number | One review's rating, 1–5. Not the product rating |
| text | text | Plain text only; never render as HTML |
| review_date | date | `YYYY-MM-DD` |
| reviewer_name | text | Empty for Demo |
| review_source | text | "Synthetic sample review (…)" |
"""

ANSWER_KEY_README = """# Answer key: test-only, not included

The Demo generator writes a separate answer key that lists the scenarios it planted in the synthetic data. It is used only by automated tests, to check the analytics against known truth.

- It is **restricted to tests and evaluation** and must never be read by application analytics or used to tune them.
- It is **not copied into this pack**, and it must not be added to teammate import data.
- To reproduce it, run the Demo generator with the seed in `manifest.json`. The project keeps it apart from the data.
"""


if __name__ == "__main__":
    from pymongo import MongoClient

    from ..settings import DataMode, Settings

    s = Settings()
    db = MongoClient(s.mongo_uri, tz_aware=True)[s.database_for(DataMode.DEMO)]
    m = export_reference(db, Path(sys.argv[1]))
    print(json.dumps({k: v.get("rows") for k, v in m["files"].items() if "rows" in v}), m["image_assets"], "images")
