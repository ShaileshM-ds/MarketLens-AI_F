# Phase 3: Product Explorer

## Pages and routes
| Route | What it shows |
| --- | --- |
| `/products` | Product Explorer: search, filters, active filter chips, sort, grid or table view, pagination. All state is in the URL (`q`, `category`, `marketplace` (repeatable), `availability` (repeatable), `min` and `max` in rupees, `prating`, `srating`, `free=1`, `sort`, `page`, `view=table`). |
| `/products/:productId` | Product details: overview and provenance, price comparison summary, one card per store listing, Price History (empty state), customer reviews (paged). |

The active workspace (Demo / Imported / Live) decides which database every request reads. Switching workspace resets the page number. Results from one workspace are never shown as a placeholder for another. A product URL opened in another workspace shows "Product not found … in <workspace> data".

## API (all read-only, `mode` = `demo` | `imported` | `live`)
| Method and path | Parameters | Returns |
| --- | --- | --- |
| `GET /api/v1/products` | `mode`, `q` (≤100 chars), `category` (launch slug), `marketplace` (repeatable), `currency` (required with price filters), `price_min_minor` / `price_max_minor` (integer minor units, ≥0), `availability` (`in_stock` / `limited_stock` / `out_of_stock` / `unknown`, repeatable), `seller_rating_min` and `product_rating_min` (0–5), `free_shipping`, `condition`, `sort`, `page` (≥1), `page_size` (1–60, default 24) | `{mode, total, page, page_size, sort, items[], semantics}` |
| `GET /api/v1/products/filters` | `mode` | Category, store, currency (min/max price), availability and condition options from the data; brand, size and colour lists (empty for this dataset); `catalog_status`; `data_basis` (`verified_history`, `snapshot_only`, `all_synthetic`) |
| `GET /api/v1/products/{product_id}` | `mode` | `{product, offers[], comparison, reviews_summary, price_history, provenance}` |
| `GET /api/v1/products/{product_id}/reviews` | `mode`, `page`, `page_size` (1–100, default 10) | `{total, page, page_size, items[]}` |

Errors: 422 for invalid parameters (unknown sort, category, availability, reversed or currency-less price range, page < 1, page_size too large, over-long IDs or searches); 404 when the product isn't in that workspace; 409 for Live while no provider is configured; 503 if MongoDB is unreachable. No MongoDB `_id`s or raw documents are returned.

## Semantics
- **Search:** exact product ID (any case) or a case-insensitive substring of the product name. Input is escaped and matched literally, never as a regular expression or query operator.
- **Store-level filters** (store, price, availability, ratings, free shipping, condition) apply **together to the same listing**. A product matches when at least one of its listings meets all of them. Card prices, store counts and ratings then use only the matching listings.
- **Price filter and card price:** the current **base listing price** (before shipping, coupons and payment offers), in one currency. Users type rupees; the browser converts them to minor units with decimal-safe parsing.
- **Availability filter:** the availability the store stated. Listings whose stock disagrees keep their stated availability and are flagged.
- **Sorting** (always deterministic; missing values last):
  - `name_asc`: name, then product ID.
  - `name_desc`: name descending, then product ID.
  - `price_asc` / `price_desc`: lowest matching base price, then name, then product ID.
  - `rating_desc`: highest single-store product rating among the matching listings, then name, then product ID. Ratings are never averaged.
  - `offers_desc`: number of matching listings, then name, then product ID.
- **Lowest prices on the details page** consider only listings that are in stock or limited stock, have a current price and carry no stock warning. Excluded listings are named with the reason.
  - **Lowest base price:** among those listings.
  - **Lowest known delivered price:** among those listings with known shipping only. When some shipping is unknown the page says so.
  - Prices in different currencies are never compared.
- **Shipping:** 0 means known free shipping. Blank means "Not stated" and the total reads "Total incomplete"; it is never treated as free or zero.
- **Coupons and payment offers** are shown as conditional and are never subtracted.
- **Ratings** stay separate: seller rating, product rating for each store, and each review's rating.
  - The review average is the arithmetic mean of valid 1–5 review ratings, rounded half-up to 2 decimals, shown with its count.
  - Below 10 reviews it carries a small-sample note.

## Current observation and price history
- For each listing:
  - **Latest verified UTC observation** (by `observed_at`) when any exist.
  - Otherwise its **single snapshot** (labelled "timezone not stated").
  - Otherwise, with several snapshots without timezones, **no current observation**: they can't be ordered, so no price is shown.
- Price History is an empty state for the imported dataset: "Verified price history is not available for this product. The current dataset contains snapshot observations without confirmed timezones."
  - No chart is drawn, and no trend, minimum, maximum or average is calculated from snapshots.

## Read model and indexes
- `product_summaries` (per workspace) is a derived read model, built from `products`, `offers`, `observations` and `reviews`, which it never modifies.
  - It's rebuilt automatically for affected products after each import.
  - Rebuild it manually with `docker compose exec api python -m app.cli rebuild-summaries --mode imported`.
  - It can be dropped and rebuilt without data loss.
- Indexes on `product_summaries`: `name_sort` (name_lower, product_id), `category_name_sort` (category, name_lower, product_id), `product_id_lower`, `offer_marketplace` (offers.marketplace), `offer_price` (offers.price_minor). No other collections' indexes changed.
- Name substring search can't use an index (unanchored match). That's fine at this size, and noted as a limit for very large catalogues.

## Images
Every product shows the local generic image (`/images/product-placeholder.svg`) captioned "No product photo in this dataset". The dataset's placeholder-host URLs are kept in the database but never loaded.
