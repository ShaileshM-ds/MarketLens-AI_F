"""Shared test helpers. The sample CSV is only ever read, never written."""

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from marketlens_core.importing.config import ImportConfig
from marketlens_core.importing.parsing import parse_file
from marketlens_core.importing.rows import RowContext

REPO = Path(__file__).resolve().parents[1]
SAMPLE_PATH = REPO / "data" / "samples" / "mens_clothing_dataset_enriched.csv"

# Fixed clock so tests are deterministic.
NOW = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)

SAMPLE_ROW = {
    "product_id": "MCL0001",
    "product_name": "Nike Men's Black Crew-Neck T-Shirt - Size S (Style 001)",
    "seller_id": "CLSEL00001",
    "seller_name": "Amazon Fashion Seller 1",
    "timestamp": "2026-11-04T10:30:00",
    "price": "1380",
    "original_price": "1600",
    "currency": "INR",
    "marketplace": "Amazon",
    "product_url": "",
    "availability": "In Stock",
    "shipping_cost": "60",
    "delivery_information": "Delivery in 2-4 days",
    "discount": "13.75",
    "seller_rating": "4.3",
    "product_rating": "3.5",
    "category": "T-Shirts",
    "source": "Generated for project demonstration",
    "source_type": "Synthetic",
    "listing_id": "AMA-CLO-LIST-000001",
    "coupon_discount": "0",
    "payment_offer": "No payment offer",
    "urgency_message": "Deal ends soon (synthetic example)",
    "stock_quantity": "8.0",
    "product_condition": "New",
    "seller_location": "Bengaluru, Karnataka",
    "last_updated": "2026-11-04T10:30:00",
    "image_url": "https://placehold.co/600x600/1A1A1A/FFFFFF.png?text=Nike+Black+Crew-Neck+T-Shirt",
    "review": "It's alright. The stitching could be better, though the fit around the shoulders is acceptable. Okay for casual use.",
    "rating": "3",
    "review_source": "Synthetic (generated sample review)",
}

SNAPSHOT_CATEGORIES = {
    c: "mens-clothing"
    for c in ["T-Shirts", "Shirts", "Jeans", "Trousers", "Hoodies & Sweatshirts", "Jackets", "Track Pants"]
}


def csv_bytes(rows: list[dict], columns: list[str] | None = None) -> bytes:
    columns = columns or list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def make_parsed(rows: list[dict]):
    return parse_file(csv_bytes(rows), "csv", max_rows=10_000)


def snapshot_config(columns, **overrides) -> ImportConfig:
    cfg = ImportConfig(
        field_map={c: c for c in columns},
        category_map=dict(SNAPSHOT_CATEGORIES),
        timestamp_policy="allow_timezone_unknown",
        declare_synthetic=False,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def history_config(columns) -> ImportConfig:
    return snapshot_config(columns, timestamp_policy="require_utc")


def ctx(**overrides) -> RowContext:
    base = dict(
        run_id="run-test",
        source_file_id="file-test",
        source_filename="sample.csv",
        now=NOW,
    )
    base.update(overrides)
    return RowContext(**base)
