# MarketLens AI: Demo reference pack

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
