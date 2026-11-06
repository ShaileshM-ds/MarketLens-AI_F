# Phase 4: Marketplace comparison and price intelligence

## Routes
| Route | What it shows |
| --- | --- |
| `/products` | Product Explorer plus: confirmed delivered price on each card, an "Add to comparison" checkbox, the comparison tray, advertised-discount and confirmed-delivered filters, 4 new sorts. |
| `/products/:id` | Nine sections with jump links: Overview, Store offers (expandable), Delivered price comparison, Discount transparency, Ratings and reviews, Shipping and delivery, Stock and availability, Data provenance, Price History. |
| `/compare?ids=A&ids=B` | Side-by-side comparison of up to 4 products: add from search, remove, replace in place, clear. The selection is kept per workspace, and the URL can be shared. |

## Pricing formulas (`shared/marketlens_core/pricing.py`)
- **Inputs:** all money is integer minor units. Non-integer, negative or boolean amounts are rejected (`ValueError`), consistent with the importer's rules.
- **Delivered price** = base price + known shipping.
  - Unknown shipping means no delivered price: "Total incomplete", "Delivered total can't be confirmed".
  - 0 shipping is known free shipping.
  - Coupons and payment offers are never subtracted.
- **Three "lowest" measures**, each listing every tied listing in listing-ID order:
  1. **Lowest listed price:** lowest base price across all listings, before shipping. Availability isn't considered.
  2. **Lowest confirmed delivered price:** across all listings with known shipping, including ones reported unavailable.
     - `certain_overall` is false when some listing has unknown shipping *and* a lower base price, since it might be cheaper delivered. A listing with unknown shipping whose base price is already higher can't be cheaper, because shipping is never negative.
  3. **Lowest confirmed delivered price among offers marked available:** only listings reported "In Stock" or "Limited Stock" in the imported snapshot, with a current price and no stock contradiction.
     - Excluded listings are returned with a reason: "Reported out of stock", "Availability and reported stock quantity disagree", "Availability not reported" or "No current price".
- **Currencies:** if listings use more than one currency, all three measures are unavailable and say why.

## Discount rules
- **Calculated reduction** = (reference − price) / reference × 100, using Decimal arithmetic and rounded half-up to 2 decimals.
  - Negative when the price is above the reference.
  - Unavailable when the reference is missing or 0.
- **Difference** = advertised % − calculated %.
  - "Consistent" when |difference| ≤ 0.5 points, the same tolerance as the importer's `discount_mismatch` check.
  - Otherwise "Differs by N points", with a neutral note that names possible causes and makes no accusation.
- **Other statuses:** `no_reference`, `no_advertised`, `price_above_reference`, `no_price`.
- **The reference price** is labelled "seller-provided reference price (M.R.P.)", not a verified past selling price.
- **Advertised promotion, calculated reduction, coupon and payment offer** are shown separately and never stacked.

## API changes (all read-only)
- `GET /api/v1/products/{id}` gains:
  - `pricing` (the three measures)
  - per-offer `delivered_price_minor`, `delivered_status`, `discount`, `flags`
  - `availability_summary` (with a `contradictions` count)
  - `quality_labels` (codes: `synthetic_dataset`, `timezone_unknown`, `shipping_unknown`, `availability_contradiction`, `missing_product_metadata`, `verified_history`)
  - `provenance.source_types`
- **New message:** `price_history.reason` now reads "Verified historical price data is not available for this product yet. Current comparisons use imported snapshot observations."
- `GET /api/v1/products` gains:
  - **Parameters:** `discount_min` / `discount_max` (advertised %, 0–100, on the same listing as the other store filters) and `delivered_known`.
  - **Sorts:** `delivered_asc`, `delivered_desc` (confirmed delivered, missing values last), `discount_desc` (highest advertised), `available_desc` (listings marked available).
  - **Item fields:** `lowest_delivered`, `available_offer_count`, `max_advertised_discount`.
  - `price_asc` / `price_desc` remain *listed* (base) price.
- **New `GET /api/v1/compare?mode=&ids=…`** (1–4 distinct IDs, each 1–128 characters; duplicates are collapsed). Returns `{products[] in request order, missing[], comparability_warnings[]}`.
  - Warnings cover different categories, sub-categories, currencies and conditions.
  - Products are matched only by stored product ID.
  - It uses a fixed number of batched queries, not one round trip per product.
  - Errors: 422 for invalid input, 409 for Live.

## Read model
- `product_summaries` **version 2** adds `delivered_minor`, `advertised_discount_percent` and `available` per listing.
- At startup the worker rebuilds summaries that are missing or out of date (`ensure_summaries_current`). Only that derived collection is written.
- No new indexes; the existing explorer indexes cover the new filters' base queries.

## Charts
- Five charts, built as accessible HTML/SVG-free bars with no chart library:
  - Confirmed delivered price by store
  - Price composition (base + shipping)
  - Advertised vs calculated discount
  - Listings by reported availability
  - Ratings by store (product rating and seller rating, never combined with review ratings)
- Each chart has a text summary and a Chart/Table toggle showing the exact figures. Unknown values get a written note, never a bar.
- There is no price-history chart: the imported observations are timezone-unknown snapshots.

## Measured performance (local Docker on Windows, 500 products)
Measured at `127.0.0.1:8080`, through nginx: 7 requests after warm-up, median.

| Request | Median |
| --- | ---: |
| List, default sort | 21 ms |
| List, 4 combined filters and delivered sort | 21 ms |
| Search and discount sort | 15 ms |
| Filter metadata | 33 ms |
| Product details | 13 ms |
| Compare 4 products | 14 ms |

Using `localhost` in curl added about 200 ms per request (an IPv6 `::1` attempt first, because ports are bound to 127.0.0.1). That's a client resolution effect, not app time.

## Not built or deferred
- **Verified price-history charts:** no qualifying data exists yet.
- **Brand, size and colour comparison:** these fields are absent from the data.
- **Compare tray on the compare page:** the page manages its own selection there.
- **Currency picker:** not built for mixed-currency datasets. The API never compares currencies.
