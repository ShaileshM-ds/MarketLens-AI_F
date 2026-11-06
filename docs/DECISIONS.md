# Decisions

## Identity
- `product_id` links the same product across Amazon, Flipkart and Myntra. It is the only cross-store link; products are never matched by title.
- `product_id`, `listing_id` and `seller_id` are preserved exactly as supplied (no trimming, case changes or renaming). Seller IDs are never merged by seller name, even when many IDs share one name.
- A listing's identity is fixed once stored: a row that links an existing `listing_id` to a different `product_id` or `seller_id` is quarantined, not applied.

## Ratings
- `rating` is ONE review's rating. Label it "Review rating N / 5".
- `product_rating` is per store unless it is confirmed to be cross-store. Show it per store and label it "Product rating".
- Never average or merge `rating` into `product_rating`.

## Missing attributes
- The first imported dataset (men's clothing snapshot) has no brand column, so brand stays blank for its records. Demo data has fictional brand names created by the generator (see docs/SCOPE.md §5), marked synthetic.
- Never guess brand, size or colour from product names (or any other free text). These fields are filled only when the data supplies them.

## Categories
- The men's clothing snapshot's sub-categories (T-Shirts, Shirts, Jeans, Trousers, Hoodies & Sweatshirts, Jackets, Track Pants) map to the launch category `mens-clothing`. Each record keeps its original sub-category separately in `source_category`.
- Category mapping is always explicit in the import configuration. A row whose category is not mapped is quarantined; it is never guessed.

## Images
- **Imported images are shown while browsing** (Explorer cards and table, product page, comparison) when the dataset's image URL is safe. It replaces the earlier rule that only the generic image was shown.
  - **Safe means:** https only, a real host, no embedded credentials, at most 2,048 characters, and the host allowed by `IMAGE_HOSTS`.
    - `*` (the default) allows any https host.
    - A comma list allows only those hosts and their subdomains.
    - An empty value shows none.
  - **What the browser gets:** the API sends `image.url` only for safe URLs. Every original URL stays stored unchanged in `image.source_url` (provenance).
  - **Loading:** images load without a referrer and fall back to the local generic image if they fail. The caption says "Image from the imported dataset".
- **Demo products** show openly licensed stock photos of *similar* products where a brand-free photo exists.
  - Source: Wikimedia Commons, CC0 or CC BY / CC BY-SA, stored locally in `frontend/public/demo-photos/` and credited in [IMAGE_CREDITS.md](IMAGE_CREDITS.md) and on the product page.
  - Each photo is captioned "Stock photo of a similar product; colour and model may differ" and falls back to the product's SVG artwork if it fails.
  - No photos of identifiable people or visible brands were used. One kurta photo is cropped on screen to the garment.
  - Phones keep their SVG artwork. External imported images need internet access; offline, the fallback is shown.
- **App-served image paths:** `/demo-images/<name>.svg|png|jpg|jpeg|webp` (files MarketLens itself serves) are also shown, under any `IMAGE_HOSTS` setting. Only that folder and those extensions qualify; no other relative paths. The example dataset's `image_url` column uses these, so its images show after import, even offline.

## Timestamps (snapshot file)
- The snapshot's timestamps have no timezone. The importer preserves the original timestamp string exactly, sets `timestamp_quality = "timezone_unknown"`, and leaves the normalized UTC observation time (`observed_at`) unknown. It never silently assumes a timezone.
- These records stay visible in the catalog but are marked `history_eligible = false` and cannot support historical analytics.
- These snapshot rules do NOT relax the strict UTC requirements for the later history file (docs/DATA_REQUIREMENTS.md). History files are imported with the `require_utc` timestamp policy, which quarantines any row without an explicit UTC timestamp.

## Observation identity and re-imports
- Observations are immutable: the importer only ever inserts them, never updates or replaces them.
- Each observation has a deterministic ID built from `listing_id` plus its time:
  - When UTC time is known: `obs1|<listing_id>|utc:<YYYY-MM-DDTHH:MM:SS.ffffffZ>`.
  - When the timezone is unknown: `obs1|<listing_id>|source-time:<original timestamp string>`.
- The two forms live in different namespaces, so a later timezone-aware history row never collides with or replaces a snapshot row, even when the clock times look the same. It is appended as a new observation.
- Re-importing the same row produces the same ID and is counted as a duplicate. If a row has the same ID but different values, it is quarantined ("stored observations are immutable") and the stored record is left unchanged.
- Reviews get a deterministic ID from their observation ID plus a hash of the review rating and text, so re-imports never duplicate reviews.

## Stock and availability
- **Snapshot imports** (`allow_timezone_unknown`): contradictions (for example "Out of Stock" with stock above zero, or "In Stock" with stock 0) are kept exactly as supplied and flagged as warnings on the observation (`flags`). They are never corrected.
- **History imports** (`require_utc`): a row whose stock and availability disagree is quarantined in `rejected_records`. The record keeps the complete original row (`raw`), its provenance (ingestion run, source file, raw source reference, row number, schema version, timestamp rule, quarantine time) and an explicit reason (`stock_availability_contradiction`). Values are never corrected. This implements docs/DATA_REQUIREMENTS.md #6.
- Blank stock stays unknown. Whole-number values written with a decimal point (for example "8.0") are accepted as integers; fractional or negative stock is quarantined.

## Money in imports
- Rupee amounts (`price`, `original_price`, `shipping_cost`, `coupon_discount`) are converted to integer minor units with decimal arithmetic (never floats). Amounts with thousands separators, currency symbols or more decimal places than the currency allows are quarantined with a plain reason.
- `original_price` becomes the reference price. `discount` stays the advertised discount percent.
- Blank shipping stays unknown; zero means known free shipping.
- Coupons and payment offers are stored as conditional offers and never reduce the displayed price.

## Provenance
- Synthetic status comes from `source_type` (values mentioning synthetic, generated or simulated mean synthetic) or from an administrator declaring the whole file synthetic. A row whose provenance can't be established is quarantined.
- Every product, offer, observation and review records the ingestion run, ingestion time, source file, raw source reference (`<file id>:<filename>#row=<n>`) and schema version. Observations keep the original row values unchanged in `raw`.

## Accounts
- User accounts and sessions live in their own MongoDB database (`marketlens_accounts`), separate from the Demo, Imported and Live data databases, so resetting Demo data never removes accounts. No default or shared administrator credentials exist; administrators are created with a command-line tool.
- Accounts and sessions created by the user are never deleted or modified by the assistant. Only temporary test accounts the assistant itself created may be removed.

## Product Explorer (Phase 3)
- **Read model.** The explorer reads a derived `product_summaries` collection in each workspace database instead of reading every observation per request (docs/SCOPE.md §8). It's built only from products, offers, observations and reviews, never modifies them, is rebuilt after each import for affected products (or with `python -m app.cli rebuild-summaries --mode <mode>`), and can be dropped and rebuilt without loss. This is the one new write in Phase 3. It resolves the brief's "read-only consumer" against SCOPE §8 and database-level filtering without changing any source data.
- **Current observation per listing:** the latest verified UTC observation; otherwise the single snapshot; otherwise none. Several snapshots without timezones are never ordered against each other.
- **Store-level filters** apply together to the same listing. Card prices are the lowest matching base listing price, labelled as excluding shipping.
- **Lowest prices on the details page** consider only purchasable listings (in stock or limited stock, current price, no stock warning). Unknown shipping is never treated as free, and currencies are never compared with each other.
- **Price history** is an empty state until verified UTC history exists. No charts or trends are derived from snapshots.
- **Images:** every product uses the local generic image until an image-host allowlist exists.

## Marketplace comparison and price intelligence (Phase 4)
- **Three named "lowest" measures** are always shown separately, never as a single "cheapest":
  1. Lowest listed price (base price, any availability).
  2. Lowest confirmed delivered price (base + known shipping, any availability). It says when unknown shipping means the overall cheapest can't be determined.
  3. Lowest confirmed delivered price among offers marked available (in stock or limited stock in the snapshot, without a stock contradiction).
  Ties list every tied listing. Different currencies are never compared.
- **Discount transparency:**
  - The calculated reduction from the *seller-provided* reference price (Decimal, half-up, 2 dp) is compared with the advertised percent.
  - Differences above 0.5 points (the importer's tolerance) are shown neutrally, without accusing the store.
  - Coupons and payment offers are conditional and never subtracted or stacked.
- **Wording.** Unknown values read "Unknown" or "Not available".
  - Unknown shipping keeps CLAUDE.md's "Total incomplete", plus "Delivered total can't be confirmed".
  - Availability is labelled "reported in imported snapshot", never live.
- **Charts** are small in-house accessible bar charts with a data-table view, instead of ECharts. SCOPE allows "ECharts or equivalent", and 3–5 bars per chart don't justify a large dependency.
- **Comparison** holds at most 4 products (SCOPE §5), matched only by product ID. The selection is kept per workspace in browser storage as a convenience, and the compare URL is the shareable source of truth.
- **Read model version 2.** The worker rebuilds out-of-date `product_summaries` at startup. That derived collection is the only thing written.

## Watchlists, alerts and notifications (Phase 5)
- **Storage.** User-owned data (watchlists, alert rules, alert events, notifications, email outbox) lives in each workspace's database, keyed by user ID, so it never crosses Demo, Imported and Live. Accounts stay in `marketlens_accounts`. Ownership is enforced in every query, and other users' records answer 404.
- **Alert type.** Only `below_target` exists: base price, or confirmed delivered price (base + *known* shipping). It's compared exactly in minor units, in the product's single currency. The other SCOPE §5 types are refused until the data or analytics they need exist.
- **No retrospective alerts.** A rule evaluates only observations inserted by an ingestion run whose ingestion time is after the rule's `active_since` (creation or resume). Existing snapshots are shown only as context. Resuming never replays.
- **Eligibility.** Listings reported out of stock, stock contradictions, unreported availability, other currencies, unknown shipping (for delivered rules) and observations after the watch-until date are excluded with a recorded reason.
- **Idempotency.** One event key per (rule, observation) is the `_id` of both the event and the notification: at most one notification per pair, and retries are safe without transactions. This is not "exactly once".
- **Re-arm and cooldown.** A rule disarms after notifying and re-arms on a later above-target observation (or manually). The cooldown blocks a second notification within N hours.
- **Wording.** "New qualifying observation detected", never "price dropped".
- **Email.** A local outbox record "not sent; nothing was sent" for each notification (SCOPE §5). No external delivery exists.
- **Signed-out taps.** A Watch tap is kept in session storage only and completed after sign-in. Return addresses are restricted to same-site paths.
- **Caching.** nginx serves `index.html` with `Cache-Control: no-cache` and hashed `/assets/` as immutable, so a new deploy is never hidden behind a stale cached app. Security headers are repeated in each location block, because a location's `add_header` replaces the server-level ones.

## History foundation
- **History** is built only from `history_eligible` observations (verified UTC time) and always takes an explicit UTC cutoff.
  - A day's value per listing is the lowest observed up to the cutoff; the product line is the lowest across listings.
  - Missing days are gaps, unknown shipping gives no delivered value, and mixed currencies give no series.
- **Time Machine:** the state at T is the latest verified observation at or before T per listing. No later observation is ever returned.
- **Demo data** is generated by the approved deterministic generator, through the normal import pipeline, into the Demo database only. Its answer key is a separate file that is never stored in a database or read by analytics.
- **Supplied review IDs** are review identity (`rev1|id:<id>`), so a review repeated on many history rows is stored once.
- **Conflicting rows:** rows that share a listing and UTC time but disagree are quarantined (`immutable_conflict`), never merged or chosen silently.
- **Chart axis labels** are HTML, not SVG text, so they stay ≥ 12 px at any chart width.

## Evidence: Real Price Detector and Genuine Discount Score
- **Comparable price** = the same store listing (seller, store, variant, currency) on the chosen basis. A day's value is the lowest usable observation that day; the usual price is the median of those days, current observation excluded.
- **Usable** observations: price known (delivered needs known shipping), in stock or limited stock, no stock contradiction. If a listing's latest observation isn't usable, it has no result: an out-of-stock or unconfirmed price is never "current".
- **Headline** = the listing with the lowest current comparable price. Listings in different currencies are never compared.
- **Thresholds** (not specified in SCOPE; conservative, versioned `evidence-1`): at least 14 distinct observed days for both detector and score; verdict "Genuine price reduction" at ≥ 5% savings, "Above its usual price" at ≤ −5%, otherwise "No real reduction"; reference increase finding at ≥ 20% above its window median.
- **Score:** savings 0% → 0 and ≥ 25% → 100; percentile counts ties half; agreement 100 when the advertised discount exceeds real savings by ≤ 5 points, 0 at ≥ 25 points. A missing advertised discount is disclosed and the remaining weights are rescaled. Bands: ≥ 70 strong, 40–69 some, < 40 little.
- **Advertised support** wording: supported, partly supported (real but smaller reduction), not supported. Coupons and payment offers are never subtracted.
- The answer key is read only in test code.

## Buying advice
- **Forecasts never decide advice.** A forecast-based expectation is shown separately, and only when the model beat the last-price baseline in backtests.
- **Classification** (`advice-1`, revised): Buy now only when real savings ≥ 5%. Otherwise Consider waiting: ordinary prices and inflated reference prices are never presented as bargains. Low confidence when the price is merely usual.
- **Abstain** (Insufficient evidence) when evidence is unavailable or insufficient, currencies are mixed, or the latest verified observation is more than 7 days before the cutoff.
- **Confidence:**
  - Starts high only for a strong signal: ≥ 10% savings with a price lower than ≥ 80% of observed days, or ≥ 10% above usual.
  - It drops one level each for: latest observation older than 48 h; more than 10% missing days in the observed range; fewer than 30 observed days; any disagreeing signal.
- **Disagreeing signals:** a raised reference price, an advertised discount not supported, the other price basis (base or delivered) reaching a different verdict, or a strong score against a wait.

## Forecasting and Future Price Memory
- **Scope of a forecast:** one store listing (the evidence headline), so seller, store and currency are never mixed. The daily value is the lowest usable verified price. Missing days are never filled; backtest points needing them are skipped.
- **Models** (`forecast-1`, no fitted parameters, deterministic): last observed price (baseline) and the 14-observed-day median. The model is used only with ≥ 5% lower backtest MAE, else the baseline (SCOPE).
- **Backtest:** rolling origin in date order; each origin sees only earlier days. At least 20 points per horizon, otherwise that horizon is unavailable. 80% range from past errors; coverage measured walk-forward and shown even when below target.
- **Abstain:** no forecast without evidence availability (≥ 14 days), with stale data (> 7 days) or mixed currencies.
- **Future Price Memory** follows SCOPE: outcomes after past drops (≥ 10% below the previous 14-day median), not forecasts. Only completed outcomes count, non-overlapping 14-day episodes, counts not probabilities. The Demo answer key is used only in tests.

## Seller synchronization and pricing audit
- **Synchronization** (`sync-1`) compares pairs of store listings on base price only (same currency, never mixed), from verified observations inside the window up to the cutoff.
  - Change events (≥ 3%, gap ≤ 2 days) are matched in the same direction within ±1 day, never by price level. Similar or equal prices alone are never a finding.
  - Listings with fewer than 14 common days, or none in the last 7 days, are insufficient. Results are patterns worth investigating, not proof.
- **Audit** (`audit-1`): findings are flags for review, not legal findings. Kinds: observed (recorded fact), calculated (Real Price Detector), heuristic (may be benign).
  - Urgency is flagged only after ≥ 14 days with the message while stock stayed normal (In Stock, stock > 5). Low stock makes the message consistent; unknown stock isn't judged.
  - Rules without the data they need are disabled. Snapshot observations (no observation time) count only if ingested by the cutoff.
- **Forecast ranges** are labelled nominal. Measured coverage is shown, with a "Not calibrated" warning when it's more than 5 points short. forecast-1 measured 75.6% / 66.0% / 52.1%; forecast-2 is in FORECAST_EVALUATION.md.

## Analyst dashboard and SCOPE alert types
- **Dashboard** figures come from the same services as product pages, at an explicit UTC cutoff. Snapshot observations count only if ingested by the cutoff and never enter historical analytics.
  - The marketplace filter limits products to those sold there and limits store counts; per-product analytics stay product-level.
  - Cached results are keyed by the latest ingestion run and method versions; nothing is served stale after an import.
- **Signal alerts** are evaluated only after imports that add verified observations for the product, ingested after the rule became active. The analysis cutoff is the latest verified observation time.
  - **State-based types** (meaningful discount, advice change, seller switch, audit finding, synchronization pattern) record a baseline on first evaluation and notify only on a real change under the same analysis version.
    - Meaningful discount re-arms when it stops qualifying.
    - Advice change ignores "Insufficient evidence" as a comparison point.
    - Seller switch compares seller IDs among fresh (≤ 7 days), in-stock verified listings in one currency.
  - **Observation-based types:**
    - New low: below every verified price of the product in the previous 90 days, with 14+ earlier observed days.
    - Restock: previous verified observation of the listing out of stock, now in or limited stock.
  - **Identity:** one evaluation record per (rule, run); notification id = hash(rule, version, state change, cutoff).

## Forecast calibration and methodology
- **Intervals** (`forecast-2`) use split-conformal quantiles of relative absolute errors |actual ÷ predicted − 1| at rank ⌈(n+1)·0.8⌉.
  - Walk-forward: only errors whose target day was observed by the origin are used.
  - With fewer than 10 errors, no range is shown.
  - This was chosen a priori as a standard method, not tuned on Demo results. Coverage is reported together with average width, and shortfalls stay visible ("Not calibrated" when more than 5 points below nominal).
- **Methodology page** values come from the code through `/api/v1/methodology`; the page never hardcodes thresholds.

## Presentation and demo reference pack
- **Model selection is per forecast series:** one store listing, so one product, seller, store and currency. It uses only that series' chronological backtest up to the cutoff.
  - The candidate is used only if it beats the last-price baseline by 5%+ there.
  - Other series never influence the choice.
  - Pooled workspace errors are reported, never used to select. (A short-lived workspace-wide gate was removed.)
- **Calibration wording:** "Not calibrated" is shown for any horizon whose measured coverage is below the nominal level, not only beyond 5 points.
- **Demo artwork:** generated, self-contained SVG (no external references or images), mapped by Demo product ID and shown only in Demo mode, with a local fallback. The Demo database is unchanged.
- **Reference pack:** an export of the Demo database only (it refuses other databases); read-only and deterministic. It excludes the answer key, user data and the observations' `raw` rows (all their values are in the columns).

## Imports go to Imported mode only
- The importer always writes to the Imported database. Demo data comes only from the demo generator, and Live data only from a configured provider.
