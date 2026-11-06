# Demo reference pack: schema

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
| observation_id | text | `obs1\|<listing_id>\|utc:<time>` |
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
| review_id | text | `rev1\|id:<external_review_id>` |
| external_review_id | text | Supplied review ID |
| product_id, listing_id, observation_id | text | → products / offers / observations |
| review_rating | number | One review's rating, 1–5. Not the product rating |
| text | text | Plain text only; never render as HTML |
| review_date | date | `YYYY-MM-DD` |
| reviewer_name | text | Empty for Demo |
| review_source | text | "Synthetic sample review (…)" |
