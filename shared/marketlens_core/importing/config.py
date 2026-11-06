"""Import configuration: field mapping, category mapping, timestamp policy."""

from dataclasses import asdict, dataclass, field

from ..catalog import LAUNCH_CATEGORIES
from ..timestamps import TIMESTAMP_POLICIES
from .parsing import ParsedFile


@dataclass(frozen=True)
class TargetField:
    name: str
    label: str
    required: bool
    help: str


TARGET_FIELDS: tuple[TargetField, ...] = (
    TargetField("product_id", "Product ID", True, "Links the same product across stores."),
    TargetField("listing_id", "Listing ID", True, "Identifies one store listing."),
    TargetField("seller_id", "Seller ID", True, "Kept exactly as supplied."),
    TargetField("marketplace", "Marketplace", True, "Store name, for example Amazon."),
    TargetField("product_name", "Product name", True, "Shown as the title. Never parsed for brand, size or colour."),
    TargetField("category", "Category", True, "Original sub-category; mapped to a launch category below."),
    TargetField("timestamp", "Observation time", True, "ISO 8601. See the timestamp rule."),
    TargetField("price", "Price", True, "Major units (rupees). Stored as integer minor units."),
    TargetField("currency", "Currency", True, "ISO code, for example INR."),
    TargetField("original_price", "Reference price", False, "Original or M.R.P. price, in rupees."),
    TargetField("shipping_cost", "Shipping cost", False, "Blank means unknown; 0 means known free."),
    TargetField("discount", "Advertised discount %", False, "Kept as the store's advertised percent."),
    TargetField("coupon_discount", "Coupon discount", False, "Conditional; never reduces the price."),
    TargetField("payment_offer", "Payment offer", False, "Conditional; kept as text."),
    TargetField("availability", "Availability", False, "Kept as supplied."),
    TargetField("stock_quantity", "Stock quantity", False, "Whole number; blank means unknown."),
    TargetField("product_condition", "Condition", False, "For example New."),
    TargetField("seller_name", "Seller name", False, "Display only; never used to merge sellers."),
    TargetField("seller_location", "Seller location", False, ""),
    TargetField("seller_rating", "Seller rating", False, "0 to 5."),
    TargetField("product_rating", "Product rating (per store)", False, "0 to 5, kept per listing."),
    TargetField("delivery_information", "Delivery information", False, ""),
    TargetField("urgency_message", "Urgency message", False, ""),
    TargetField("product_url", "Product URL", False, "http or https only."),
    TargetField("image_url", "Image URL", False, "Placeholder hosts use a local generic image."),
    TargetField("last_updated", "Last updated (as supplied)", False, "Kept as text."),
    TargetField("brand", "Brand", False, "Only when the file has a brand column."),
    TargetField("size", "Size", False, "Only when the file has a size column."),
    TargetField("colour", "Colour", False, "Only when the file has a colour column."),
    TargetField("storage", "Storage", False, "Only when the file has a storage column (for example phones)."),
    TargetField("review", "Review text", False, "Plain text; one review per row."),
    TargetField("rating", "Review rating", False, "One review's rating, 1 to 5."),
    TargetField("review_source", "Review source", False, ""),
    TargetField("review_id", "Review ID", False, "When supplied, repeated rows with the same ID are one review."),
    TargetField("review_date", "Review date", False, "ISO date (YYYY-MM-DD); shown only when supplied."),
    TargetField("reviewer_name", "Reviewer name", False, "Shown only when supplied."),
    TargetField("source", "Source", False, "Provenance label."),
    TargetField("source_type", "Source type", False, "Synthetic, generated or simulated means synthetic."),
)
TARGETS = {t.name: t for t in TARGET_FIELDS}
LAUNCH_SLUGS = {c.slug for c in LAUNCH_CATEGORIES}

# The supplied men's clothing snapshot (docs/DECISIONS.md).
MENS_SNAPSHOT_COLUMNS = frozenset(
    "product_id product_name seller_id seller_name timestamp price original_price currency marketplace "
    "product_url availability shipping_cost delivery_information discount seller_rating product_rating "
    "category source source_type listing_id coupon_discount payment_offer urgency_message stock_quantity "
    "product_condition seller_location last_updated image_url review rating review_source".split()
)
MENS_SNAPSHOT_CATEGORIES = {
    "T-Shirts": "mens-clothing",
    "Shirts": "mens-clothing",
    "Jeans": "mens-clothing",
    "Trousers": "mens-clothing",
    "Hoodies & Sweatshirts": "mens-clothing",
    "Jackets": "mens-clothing",
    "Track Pants": "mens-clothing",
}


@dataclass
class ImportConfig:
    field_map: dict[str, str | None]  # target field -> source column (None = not supplied)
    category_map: dict[str, str] = field(default_factory=dict)  # source category -> launch slug
    timestamp_policy: str = "require_utc"
    declare_synthetic: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ImportConfig":
        return cls(
            field_map={str(k): (v or None) for k, v in dict(data.get("field_map") or {}).items()},
            category_map={str(k): str(v) for k, v in dict(data.get("category_map") or {}).items() if v},
            timestamp_policy=str(data.get("timestamp_policy") or "require_utc"),
            declare_synthetic=bool(data.get("declare_synthetic", False)),
        )


def suggest_config(parsed: ParsedFile) -> tuple[ImportConfig, str | None]:
    """Exact (case-insensitive) column-name matches only; nothing is guessed from values."""
    by_lower = {c.lower(): c for c in parsed.columns}
    field_map = {t.name: by_lower.get(t.name) for t in TARGET_FIELDS}
    if set(parsed.columns) == MENS_SNAPSHOT_COLUMNS:
        present = {r.values.get("category", "") for r in parsed.rows}
        cats = {c: s for c, s in MENS_SNAPSHOT_CATEGORIES.items() if c in present}
        return (
            ImportConfig(field_map, cats, timestamp_policy="allow_timezone_unknown"),
            "mens-clothing-snapshot",
        )
    return ImportConfig(field_map), None


def source_categories(parsed: ParsedFile, config: ImportConfig) -> list[str]:
    col = config.field_map.get("category")
    if not col:
        return []
    return sorted({r.values.get(col, "").strip() for r in parsed.rows} - {""})


def config_problems(config: ImportConfig, columns: list[str]) -> list[str]:
    problems = []
    for t in TARGET_FIELDS:
        col = config.field_map.get(t.name)
        if t.required and not col:
            problems.append(f"{t.label} must be mapped to a column.")
        if col and col not in columns:
            problems.append(f"{t.label} is mapped to '{col}', which is not a column in this file.")
    unknown = sorted(set(config.field_map) - set(TARGETS))
    if unknown:
        problems.append(f"Unknown target fields: {', '.join(unknown)}.")
    bad = sorted({v for v in config.category_map.values() if v not in LAUNCH_SLUGS})
    if bad:
        problems.append(f"Category mapping uses {', '.join(repr(b) for b in bad)}, which is not a launch category.")
    if config.timestamp_policy not in TIMESTAMP_POLICIES:
        problems.append(f"Timestamp rule must be one of: {', '.join(TIMESTAMP_POLICIES)}.")
    return problems
