"""Map one parsed row to product / offer / observation / review documents.

Pure: no database access. Reasons (quarantine) and warnings are plain language.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from ..money import MoneyError, minor_digits, to_minor_units
from ..timestamps import ParsedTimestamp, TimestampError, parse_source_timestamp
from . import SCHEMA_VERSION
from .config import ImportConfig
from .parsing import ParsedRow

SYNTHETIC_PATTERN = re.compile(r"synthetic|generated|simulated", re.I)
PLACEHOLDER_IMAGE_HOSTS = {"placehold.co", "placehold.it", "placeholder.com", "via.placeholder.com", "dummyimage.com"}

REASON_LABELS = {
    "row_shape": "Row is malformed",
    "missing_field": "Required value is blank",
    "invalid_money": "Amount is not valid",
    "unsupported_currency": "Currency is not supported",
    "invalid_timestamp": "Timestamp is not usable",
    "invalid_number": "Number is not valid",
    "unmapped_category": "Category is not mapped",
    "provenance_unknown": "Provenance can't be established",
    "listing_identity_conflict": "Listing already belongs to another product or seller",
    "immutable_conflict": "Conflicts with a stored observation",
    "stock_availability_contradiction": "Stock and availability disagree (history file)",
}
WARNING_LABELS = {
    "stock_availability_contradiction": "Stock and availability disagree",
    "price_above_reference": "Price is above the reference price",
    "discount_mismatch": "Advertised discount differs from the price difference",
    "product_name_mismatch": "Product name differs from the stored product",
    "product_category_mismatch": "Category differs from the stored product",
    "product_url_not_http": "Product URL is not an http(s) address",
}
# Warnings that describe the observation itself and are stored on it.
OBSERVATION_FLAGS = {"stock_availability_contradiction", "price_above_reference", "discount_mismatch"}


@dataclass(frozen=True)
class Issue:
    code: str
    message: str


@dataclass
class RowContext:
    run_id: str
    source_file_id: str
    source_filename: str
    now: datetime
    schema_version: str = SCHEMA_VERSION
    timestamp_policy: str | None = None


@dataclass
class RowResult:
    row_number: int
    raw: dict[str, str]
    reasons: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    product: dict | None = None
    offer: dict | None = None
    observation: dict | None = None
    review: dict | None = None

    @property
    def ok(self) -> bool:
        return not self.reasons


def observation_id(listing_id: str, ts: ParsedTimestamp) -> str:
    """Deterministic identity. UTC and timezone-unknown times use different namespaces."""
    if ts.observed_at is None:
        return f"obs1|{listing_id}|source-time:{ts.raw}"
    return f"obs1|{listing_id}|utc:{ts.observed_at.strftime('%Y-%m-%dT%H:%M:%S.%fZ')}"


def review_id(obs_id: str, rating: int | None, text: str) -> str:
    digest = hashlib.sha256(f"{rating}|{text}".encode("utf-8")).hexdigest()[:16]
    return f"rev1|{obs_id}|{digest}"


def content_hash(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _image(url: str) -> dict:
    if not url:
        return {"kind": "none", "source_url": None}
    host = (urlparse(url).hostname or "").lower()
    if host in PLACEHOLDER_IMAGE_HOSTS:
        return {"kind": "generic_placeholder", "source_url": url}
    # Not on any allowlist yet: shown with the generic image, original kept.
    return {"kind": "external_unverified", "source_url": url}


def map_row(row: ParsedRow, config: ImportConfig, ctx: RowContext) -> RowResult:
    res = RowResult(row_number=row.number, raw=dict(row.values))
    reasons, warnings = res.reasons, res.warnings
    for p in row.problems:
        reasons.append(Issue("row_shape", p))

    def exact(target: str) -> str:
        """IDs: preserved exactly as supplied."""
        col = config.field_map.get(target)
        return row.values.get(col, "") if col else ""

    def get(target: str) -> str:
        return exact(target).strip()

    def text_or_none(target: str) -> str | None:
        v = get(target)
        return v or None

    # Identity -------------------------------------------------------------
    ids = {}
    for target, label in (
        ("product_id", "product ID"),
        ("listing_id", "listing ID"),
        ("seller_id", "seller ID"),
    ):
        v = exact(target)
        if not v.strip():
            reasons.append(Issue("missing_field", f"{label} is blank"))
        ids[target] = v
    for target, label in (("marketplace", "marketplace"), ("product_name", "product name")):
        if not get(target):
            reasons.append(Issue("missing_field", f"{label} is blank"))

    # Money ------------------------------------------------------------------
    currency = get("currency").upper()
    currency_ok = False
    if not currency:
        reasons.append(Issue("missing_field", "currency is blank"))
    else:
        try:
            minor_digits(currency)
            currency_ok = True
        except MoneyError as exc:
            reasons.append(Issue("unsupported_currency", str(exc)))

    def money(target: str, label: str, required: bool = False) -> int | None:
        v = get(target)
        if not v:
            if required:
                reasons.append(Issue("missing_field", f"{label} is blank"))
            return None
        if not currency_ok:
            return None
        try:
            return to_minor_units(v, currency, field=label)
        except MoneyError as exc:
            reasons.append(Issue("invalid_money", str(exc)))
            return None

    price = money("price", "price", required=True)
    reference = money("original_price", "reference price (original_price)")
    shipping = money("shipping_cost", "shipping cost")
    coupon = money("coupon_discount", "coupon discount")

    # Numbers ----------------------------------------------------------------
    def decimal(target: str, label: str, lo: float, hi: float) -> Decimal | None:
        v = get(target)
        if not v:
            return None
        try:
            d = Decimal(v)
            if not d.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            reasons.append(Issue("invalid_number", f"{label} '{v}' is not a number"))
            return None
        if not (Decimal(str(lo)) <= d <= Decimal(str(hi))):
            reasons.append(Issue("invalid_number", f"{label} '{v}' must be between {lo:g} and {hi:g}"))
            return None
        return d

    discount = decimal("discount", "advertised discount percent", 0, 100)
    seller_rating = decimal("seller_rating", "seller rating", 0, 5)
    product_rating = decimal("product_rating", "product rating", 0, 5)

    stock = None
    stock_text = get("stock_quantity")
    if stock_text:
        try:
            d = Decimal(stock_text)
            if not d.is_finite() or d != d.to_integral_value() or d < 0:
                raise InvalidOperation
            stock = int(d)
        except InvalidOperation:
            reasons.append(Issue("invalid_number", f"stock quantity '{stock_text}' must be a whole number of 0 or more"))

    review_text = get("review")
    rating_text = get("rating")
    review_rating = None
    if rating_text:
        try:
            d = Decimal(rating_text)
            if d != d.to_integral_value() or not (1 <= d <= 5):
                raise InvalidOperation
            review_rating = int(d)
        except InvalidOperation:
            reasons.append(Issue("invalid_number", f"review rating '{rating_text}' must be a whole number from 1 to 5"))

    # Time -------------------------------------------------------------------
    ts = None
    try:
        ts = parse_source_timestamp(get("timestamp"), config.timestamp_policy, ctx.now)  # type: ignore[arg-type]
    except TimestampError as exc:
        reasons.append(Issue("invalid_timestamp", str(exc)))

    # Category ---------------------------------------------------------------
    source_category = get("category")
    category = None
    if not source_category:
        reasons.append(Issue("missing_field", "category is blank"))
    elif source_category not in config.category_map:
        reasons.append(Issue("unmapped_category", f"category '{source_category}' is not mapped to a launch category"))
    else:
        category = config.category_map[source_category]

    # Provenance -------------------------------------------------------------
    source = text_or_none("source")
    source_type = text_or_none("source_type")
    synthetic = None
    if config.declare_synthetic:
        synthetic = True
    elif source_type:
        synthetic = bool(SYNTHETIC_PATTERN.search(source_type))
    else:
        reasons.append(
            Issue("provenance_unknown", "source type is blank, so it can't be established whether the row is synthetic")
        )
    review_source = text_or_none("review_source")
    external_review_id = text_or_none("review_id")
    reviewer_name = text_or_none("reviewer_name")
    review_date = text_or_none("review_date")
    if review_date:
        try:
            review_date = date.fromisoformat(review_date).isoformat()
        except ValueError:
            reasons.append(Issue("invalid_timestamp", f"review date '{review_date}' is not an ISO date (YYYY-MM-DD)"))

    if reasons:
        return res

    # Stock vs availability: snapshot keeps it as a warning; history quarantines it.
    availability = text_or_none("availability")
    a = (availability or "").lower()
    if stock is not None and (
        (a.startswith("out of stock") and stock > 0) or (a in ("in stock", "limited stock") and stock == 0)
    ):
        contradiction = f"Availability is '{availability}' but stock quantity is {stock}"
        if config.timestamp_policy == "require_utc":
            reasons.append(
                Issue(
                    "stock_availability_contradiction",
                    f"{contradiction}; history files must have consistent stock and availability, "
                    "so the row was quarantined unchanged",
                )
            )
            return res
        warnings.append(Issue("stock_availability_contradiction", contradiction))

    # Other warnings (kept, never corrected) ---------------------------------
    if reference is not None and price is not None and price > reference:
        warnings.append(Issue("price_above_reference", "Price is above the reference price"))
    if discount is not None and reference and price is not None:
        actual = (Decimal(reference - price) / Decimal(reference)) * 100
        if abs(actual - discount) > Decimal("0.5"):
            warnings.append(
                Issue("discount_mismatch", f"Advertised discount is {discount}% but the price is {actual:.2f}% below the reference")
            )
    product_url = text_or_none("product_url")
    if product_url and urlparse(product_url).scheme not in ("http", "https"):
        warnings.append(Issue("product_url_not_http", "Product URL is not an http(s) address and was not stored as a link"))
        product_url = None

    # Documents --------------------------------------------------------------
    assert ts is not None and synthetic is not None
    source_label = source or source_type or f"Uploaded file {ctx.source_filename}"
    provenance = {
        "ingestion_run_id": ctx.run_id,
        "source_file_id": ctx.source_file_id,
        "source_filename": ctx.source_filename,
        "raw_source_ref": f"{ctx.source_file_id}:{ctx.source_filename}#row={row.number}",
        "row_number": row.number,
        "schema_version": ctx.schema_version,
        "ingested_at": ctx.now,
    }
    common = {"synthetic": synthetic, "source": source, "source_type": source_type, "source_label": source_label}
    pid, lid, sid = ids["product_id"], ids["listing_id"], ids["seller_id"]
    condition = text_or_none("product_condition")

    res.product = {
        "_id": pid,
        "product_id": pid,
        "name": get("product_name"),
        "brand": text_or_none("brand"),
        "size": text_or_none("size"),
        "colour": text_or_none("colour"),
        "storage": text_or_none("storage"),
        "category": category,
        "source_category": source_category,
        "image": _image(get("image_url")),
        **common,
        "provenance": provenance,
    }
    res.offer = {
        "_id": lid,
        "listing_id": lid,
        "product_id": pid,
        "seller_id": sid,
        "seller_name": text_or_none("seller_name"),
        "marketplace": get("marketplace"),
        "product_url": product_url,
        "condition": condition,
        **common,
        "provenance": provenance,
    }
    oid = observation_id(lid, ts)
    content = {
        "listing_id": lid,
        "product_id": pid,
        "seller_id": sid,
        "marketplace": get("marketplace"),
        "source_timestamp": ts.raw,
        "observed_at": ts.observed_at,
        "timestamp_quality": ts.quality,
        "history_eligible": ts.observed_at is not None,
        "source_last_updated": text_or_none("last_updated"),
        "currency": currency,
        "price_minor": price,
        "reference_price_minor": reference,
        "shipping_minor": shipping,
        "shipping_known": shipping is not None,
        "advertised_discount_percent": float(discount) if discount is not None else None,
        "coupon_discount_minor": coupon,
        "payment_offer": text_or_none("payment_offer"),
        "offers_applied_to_price": False,
        "availability": availability,
        "stock_quantity": stock,
        "condition": condition,
        "delivery_information": text_or_none("delivery_information"),
        "urgency_message": text_or_none("urgency_message"),
        "seller_location": text_or_none("seller_location"),
        "seller_rating": float(seller_rating) if seller_rating is not None else None,
        "product_rating": float(product_rating) if product_rating is not None else None,
        "flags": [w.code for w in warnings if w.code in OBSERVATION_FLAGS],
        **common,
    }
    res.observation = {
        "_id": oid,
        **content,
        "content_hash": content_hash(content),
        "provenance": provenance,
        "raw": dict(row.values),
    }
    if review_text or review_rating is not None:
        res.review = {
            # A supplied review ID is the identity, so a review repeated on many rows is stored once.
            "_id": f"rev1|id:{external_review_id}" if external_review_id else review_id(oid, review_rating, review_text),
            "external_review_id": external_review_id,
            "product_id": pid,
            "listing_id": lid,
            "observation_id": oid,
            "review_rating": review_rating,
            "text": review_text,  # plain text; rendered as text only
            "review_source": review_source,
            "reviewer_name": reviewer_name,
            "review_date": review_date,
            "synthetic": synthetic or bool(review_source and SYNTHETIC_PATTERN.search(review_source)),
            "source": source,
            "source_type": source_type,
            "source_label": source_label,
            "provenance": provenance,
        }
    return res
