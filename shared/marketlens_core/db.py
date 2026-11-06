"""Collections and indexes. Each data mode has its own database with the same layout."""

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from .settings import DataMode, Settings

PRODUCTS = "products"
OFFERS = "offers"
OBSERVATIONS = "observations"  # immutable: insert-only
REVIEWS = "reviews"
INGESTION_RUNS = "ingestion_runs"
REJECTED_RECORDS = "rejected_records"
SOURCE_FILES = "source_files"  # original uploaded files, unchanged
JOBS = "jobs"  # database-backed worker jobs
PRODUCT_SUMMARIES = "product_summaries"  # derived read model for the explorer; rebuildable
# User-owned data (Phase 5). Stored per workspace so it never crosses Demo / Imported / Live.
WATCHLIST_ITEMS = "watchlist_items"
ALERT_RULES = "alert_rules"
ALERT_EVENTS = "alert_events"  # one per (rule, observation) evaluated; the idempotency record
NOTIFICATIONS = "notifications"
EMAIL_OUTBOX = "email_outbox"  # local record only; nothing is ever sent

MODE_COLLECTIONS = (
    PRODUCTS, OFFERS, OBSERVATIONS, REVIEWS, INGESTION_RUNS, REJECTED_RECORDS, SOURCE_FILES, JOBS, PRODUCT_SUMMARIES,
    WATCHLIST_ITEMS, ALERT_RULES, ALERT_EVENTS, NOTIFICATIONS, EMAIL_OUTBOX,
)


def ensure_mode_indexes(db: Database) -> None:
    existing = set(db.list_collection_names())
    for name in MODE_COLLECTIONS:
        if name not in existing:
            db.create_collection(name)

    db[PRODUCTS].create_index([("category", ASCENDING), ("source_category", ASCENDING)], name="category_source")
    db[OFFERS].create_index([("product_id", ASCENDING)], name="product_id_1")
    db[OFFERS].create_index([("seller_id", ASCENDING)], name="seller_id_1")
    db[OFFERS].create_index([("marketplace", ASCENDING)], name="marketplace_1")
    db[OBSERVATIONS].create_index([("listing_id", ASCENDING), ("observed_at", ASCENDING)], name="listing_observed_at")
    db[OBSERVATIONS].create_index([("product_id", ASCENDING), ("observed_at", ASCENDING)], name="product_observed_at")
    db[OBSERVATIONS].create_index([("seller_id", ASCENDING), ("observed_at", ASCENDING)], name="seller_observed_at")
    db[OBSERVATIONS].create_index([("listing_id", ASCENDING), ("source_timestamp", ASCENDING)], name="listing_source_time")
    db[OBSERVATIONS].create_index([("provenance.ingestion_run_id", ASCENDING)], name="run")
    db[REVIEWS].create_index([("product_id", ASCENDING)], name="product_id_1")
    db[REVIEWS].create_index([("listing_id", ASCENDING)], name="listing_id_1")
    db[INGESTION_RUNS].create_index([("created_at", DESCENDING)], name="created_at_desc")
    db[INGESTION_RUNS].create_index([("file.sha256", ASCENDING)], name="file_sha256")
    db[REJECTED_RECORDS].create_index([("run_id", ASCENDING), ("row_number", ASCENDING)], name="run_row")
    db[JOBS].create_index([("status", ASCENDING), ("created_at", ASCENDING)], name="status_created")
    # Explorer read model (index creation never changes documents).
    db[PRODUCT_SUMMARIES].create_index([("name_lower", ASCENDING), ("product_id", ASCENDING)], name="name_sort")
    db[PRODUCT_SUMMARIES].create_index(
        [("category", ASCENDING), ("name_lower", ASCENDING), ("product_id", ASCENDING)], name="category_name_sort"
    )
    db[PRODUCT_SUMMARIES].create_index([("product_id_lower", ASCENDING)], name="product_id_lower")
    db[PRODUCT_SUMMARIES].create_index([("offers.marketplace", ASCENDING)], name="offer_marketplace")
    db[PRODUCT_SUMMARIES].create_index([("offers.price_minor", ASCENDING)], name="offer_price")
    # Watchlists, alerts, notifications.
    db[WATCHLIST_ITEMS].create_index([("user_id", ASCENDING), ("product_id", ASCENDING)], unique=True, name="user_product")
    db[WATCHLIST_ITEMS].create_index([("user_id", ASCENDING), ("added_at", DESCENDING)], name="user_added")
    db[ALERT_RULES].create_index([("user_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], name="user_rules")
    db[ALERT_RULES].create_index([("product_id", ASCENDING), ("status", ASCENDING), ("enabled", ASCENDING)], name="eval_candidates")
    db[ALERT_EVENTS].create_index([("rule_id", ASCENDING), ("evaluated_at", DESCENDING)], name="rule_history")
    db[NOTIFICATIONS].create_index([("user_id", ASCENDING), ("dismissed_at", ASCENDING), ("created_at", DESCENDING)], name="user_history")
    db[NOTIFICATIONS].create_index([("user_id", ASCENDING), ("read_at", ASCENDING)], name="user_unread")
    db[EMAIL_OUTBOX].create_index([("notification_id", ASCENDING)], unique=True, name="notification")


def ensure_account_indexes(db: Database) -> None:
    db.sessions.create_index("expires_at", expireAfterSeconds=0, name="ttl")
    db.sessions.create_index("user_id", name="user_id_1")


def prepare_databases(client: MongoClient, settings: Settings) -> None:
    for mode in DataMode:
        ensure_mode_indexes(client[settings.database_for(mode)])
    ensure_account_indexes(client[settings.mongo_db_accounts])
