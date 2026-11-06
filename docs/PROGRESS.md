# Progress

## Phase 1: Scaffold and shell (done)
- Monorepo: `frontend/` (React + TypeScript + Vite), `backend/` (FastAPI), `worker/` (Python), `shared/` (`marketlens_core`, logic shared by API and worker), Docker Compose with MongoDB.
- `GET /api/v1/health`, `GET /api/v1/categories?mode=`.
- App shell: sidebar, data-mode switcher and badge, theme toggle, alerts bell, URL routing, Home screen, light and dark themes.

## Phase 2: Database collections and importer (accepted)

Accepted by the user, with one documented limitation: choosing a file and confirming an import in the browser were not tested by hand.

### Manual verification reported by the user
- Admin sign-in worked.
- The Import Wizard duplicate workflow was checked by hand: re-importing the existing file created zero new records, all 1,500 rows were recognised as duplicates, and 44 warning rows were identified.
- Core collection counts were checked; the Demo and Live core collections are empty.
- The invalid-data UI test was **skipped at the user's request** (not passed).

### Follow-up decision applied before Phase 3
- History imports (`require_utc`) now quarantine rows whose stock and availability disagree. Each record keeps the complete original row, its provenance and an explicit reason (DATA_REQUIREMENTS.md #6). Snapshot imports still keep these rows as warnings. Tests: 85 passed (82 earlier plus 3 new).
- The account and active session the user created are kept and were not touched.

### Built
- **Collections and indexes**, created identically in each of the Demo, Imported and Live databases (`shared/marketlens_core/db.py`): `products`, `offers` (listings), `observations` (insert-only), `reviews`, `ingestion_runs`, `rejected_records`, plus `source_files` (original uploads, unchanged) and `jobs` (worker queue).
- **Accounts** in a separate `marketlens_accounts` database: scrypt password hashes, HttpOnly SameSite=Strict session cookie (only its hash is stored, with a TTL), roles consumer / analyst / admin, sign-in throttling, and a cross-site write guard. Admins are created with `python -m app.cli create-user`; no default credentials exist.
- **Importer** (`shared/marketlens_core/importing/`) for CSV, JSON and JSONL: parse → profile → map → evaluate → apply. Preview and the real import use the same evaluation. Imports run as database-backed jobs in the worker and always write to the Imported database.
- **Admin API** (`/api/v1/admin/imports…`, admin only): upload + profile, save mapping → preview and validation, confirm, run status and summary, paged quarantined rows.
- **Wizard UI** at Data administration → New import: Choose file → Profile → Map fields → Preview → Validation → Confirm → Results. It shows summaries and tables, not raw JSON, and the step and run are kept in the URL.
- Decisions recorded in `docs/DECISIONS.md`: timestamps, categories, images, IDs, contradictions, observation identity, money, provenance, accounts.

### Verified
- `pytest`: 82 passed, 0 failed, 0 skipped. The suite covers money, timestamps, parsing, row mapping, real-MongoDB importer behaviour (duplicates, immutable appends, conflicts, quarantine, mode isolation) and the admin API (access control, cookies, cross-site block, full wizard).
- The sample was imported into Imported mode through the HTTP wizard API (via the nginx proxy and the worker):
  - **First import:** 1,500 rows; 1,500 accepted, 0 duplicate, 0 rejected; 44 rows with warnings, 44 warnings in total (all stock/availability contradictions).
  - **Stored:** 500 products, 1,500 listings, 1,500 observations, 1,500 reviews.
  - **Second import of the same file:** 0 accepted, 1,500 duplicate, 0 rejected, 1,500 duplicate reviews; nothing created; counts unchanged.
  - **Demo and Live databases:** 0 documents in every collection before and after.

### Not done or not verified
- **Wizard UI, checked in the browser while signed in** as a temporary local admin (deleted afterwards). Checked: the runs table, plus the Profile, Map fields (read-only once confirmed), Preview, Validation, Confirm and Results steps for both imports. Smallest text is 12px, there's no page-level horizontal scroll, and every control is labelled. Fixed: Preview and Validation on a confirmed import now say they show the pre-import check.
- **Not checked by hand in the browser:** choosing a file, saving a mapping and confirming. The browser pane can't attach files, and I didn't want to add test imports to Imported. These steps are covered by the API tests and the two real imports.
- Imports aren't wrapped in a transaction (standalone MongoDB). Re-running an interrupted import is safe because every identity is deterministic and observations are insert-only.
- The sign-in throttle is in memory (per API process). General API rate limits and a URL allowlist for external images aren't built yet.
- Analysts and consumers have no screens of their own yet. There's no sign-up flow; accounts come from the CLI.

## Phase 3: Product Explorer (done, awaiting review)

Details: [PHASE3_PRODUCT_EXPLORER.md](PHASE3_PRODUCT_EXPLORER.md).

### Built
- `GET /api/v1/products`, `/products/filters`, `/products/{id}`, `/products/{id}/reviews`. All read-only and scoped to the requested workspace.
- Derived `product_summaries` read model with 5 indexes, rebuilt after imports or with `python -m app.cli rebuild-summaries --mode <mode>`.
- Product Explorer at `/products`:
  - Search (debounced, Enter, clear).
  - Filters: category, store, base price in rupees, availability, product and seller rating, known free shipping.
  - Filter chips and Clear all; 6 sort orders; grid and table views; server-side pagination.
  - URL state; mobile filter drawer.
  - Loading, empty, error and retry states.
- Product details at `/products/:id`:
  - Provenance, and a price comparison (lowest base and lowest known delivered price, among purchasable listings).
  - One card per store with every observation field, conditional offers, warnings, and the observation time with its timezone status.
  - Price History empty state.
  - Paged plain-text reviews, with the average formula and sample size.
- Frontend test tooling: Vitest, Testing Library and jsdom (dev dependencies only).

### Test-first record
1. Backend tests written first.
   - `test_explorer_core.py` failed at collection: no `marketlens_core.explorer` module.
   - `test_products_api.py`: 23 failed with 404 (no routes). 1 passed, the integrity check, which passes trivially before any requests.
   - Implemented; the suite then passed except one assertion error in my own test. Every product name contains a literal "(", so a literal search for "(" correctly matches all 500. I fixed the test to compare against the literal containment count.
2. Frontend tests written first. `explorerParams` was missing, and 22 page tests failed against the Phase 1 stubs. `money.test.ts` (4) passed against the existing formatter. Implemented; then all passed.
   - One test helper was adjusted to read a focused control's accessible label instead of its text.
3. Added after the browser check: `queryClient.test.ts` (2) failed first (missing module), then passed. 4xx responses are no longer retried.

### Results
- **Backend `pytest`:** 125 passed, 0 failed, 0 skipped (85 before Phase 3 + 40 new).
- **Frontend `vitest`:** 37 passed in 5 files.
- **`npm run build`** (typecheck + production build): succeeds.

### Database integrity (MongoDB `dbHash` and counts, before and after Phase 3)
| Collection | Imported | Demo | Live |
| --- | ---: | ---: | ---: |
| products | 500 → 500 (hash unchanged) | 0 → 0 | 0 → 0 |
| offers | 1,500 → 1,500 (hash unchanged) | 0 → 0 | 0 → 0 |
| observations | 1,500 → 1,500 (hash unchanged) | 0 → 0 | 0 → 0 |
| reviews | 1,500 → 1,500 (hash unchanged) | 0 → 0 | 0 → 0 |
| ingestion_runs / rejected_records / source_files / jobs | 3 / 0 / 3 / 3 (hashes unchanged) | 0 | 0 |
| product_summaries (derived, new) | 0 → 500 | 0 | 0 |

`marketlens_accounts`: 1 user and 1 session, unchanged. API tests also check that no request modifies any document.

### Browser verification (running Docker app, Imported mode, no sign-in needed)
- **Verified:**
  - Imported shows 500 products with the synthetic and snapshot disclosures.
  - Search for MCL0001 finds 1 product. The Amazon filter shows ₹1,380 and "1 of 3 stores match". Price sort works (₹510, ₹520…). Page 2 of 21 works.
  - MCL0001 details: Amazon ₹1,380 + ₹60 = ₹1,440; Flipkart ₹1,370 + ₹60 = ₹1,430 (lowest base and lowest delivered); Myntra ₹1,480 with free shipping. Seller and listing IDs, "timezone not stated" times, Price History empty state with no chart, and reviews with store and synthetic labels are all shown.
  - The stock contradiction on MCL0222 (Myntra) is flagged, its stock is uncorrected, and it's excluded from lowest prices with a reason.
  - Back navigation works.
  - Demo shows an empty state with no stale data. Live can't be selected and explains why. Imported restores the data. A product URL in Demo shows "Product not found".
  - At 1440, 1024, 768 and 375 px: no horizontal scroll and smallest text 12px. Filters sit inline at 1024px and up and become a drawer at 768 and 375px; the drawer opens as a dialog, takes focus and closes with Escape.
  - Console errors are only the expected 401 (signed-out check from earlier) and the deliberate 404s.
- **Not verified by hand:** keyboard-only tabbing in the real browser (covered by a component test), screen-reader announcements, the dark theme on the new pages.
- **Skipped:** none.

### Known limitations
- **Live:** cannot be selected (no provider), so its "empty state" is the explanation; the API returns 409.
- **Name search:** an unanchored substring match that can't use an index. Fine for 500 products; revisit for large catalogues.
- **Brand, size and colour filters:** not built. The dataset has none; the API reports empty lists and the UI says so.
- **Currency:** price filters use the dataset's single currency (INR). There's no currency picker yet for mixed-currency data, though the API never mixes currencies.
- **Not built:** compare tray, Track price, and the Timeline/Evidence/Forecast tabs. These belong to later phases (comparison, watchlists, analytics).

## Phase 4: Advanced marketplace comparison and price intelligence (done, awaiting review)

### Scope review
- SCOPE.md already includes product comparison ("up to 4 products, with warnings when variants, conditions or currencies are not comparable") and a discount filter, so Phase 4 fits the documented roadmap.
- SCOPE's history-based analytics (Real Price Detector, Genuine Discount Score) need at least 14 days of verified history. The imported data has none, so they stay out of scope. Phase 4's discount analysis compares against the **seller-provided reference price only** and is labelled that way.
- SCOPE names "ECharts or equivalent". The Phase 4 charts have 3–4 bars per product, so they're built as small accessible SVG/HTML bars with data tables, without a new chart dependency (see DECISIONS.md).

### Baseline (5 Nov 2026, before Phase 4)
| Database | products | offers | observations | reviews | ingestion_runs | rejected_records | source_files | jobs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| marketlens_imported | 500 | 1,500 | 1,500 | 1,500 | 5 | 12,715 | 5 | 4 |
| marketlens_demo | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| marketlens_live | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

- **Difference from the Phase 3 report** (3 runs, 0 rejected records, 3 files, 3 jobs). Since then the user (`admin`) did three things:
  - Re-imported the men's clothing file (all 1,500 rows duplicates).
  - Profiled `personal_care_real_product_catalog_with_image_urls.csv` without importing it.
  - Imported `womens_clothing_all_in_one.csv` with the history rule. All 12,715 rows were quarantined as `unmapped_category`, so no products were added.
  These records are kept as they are.
- Products, offers, observations and reviews have the same `dbHash` values as in Phase 3. There are 44 contradiction flags. All observations are `timezone_unknown`, and none are history-eligible.
- `marketlens_accounts`: 1 user, 1 session (kept).

### Plan
- **4A:** audit and baseline (this section).
- **4B:** pricing and discount service, test-first: delivered price, reference-price reduction, advertised vs calculated discount, and the three "lowest" designations with ties, unavailable offers and unknown-shipping certainty.
- **4C:** extend the product details API (pricing, discount analysis, availability, quality labels) and the explorer list (delivered-price and discount sorts and filters, available-offer counts).
- **4D:** `GET /api/v1/compare` for up to 4 products, plus a compare tray, compare page, add / remove / replace / reset.
- **4E:** product page sections and charts: delivered price, price composition, discount, availability, ratings.
- **4F:** responsive layout, themes, accessibility, reduced motion.
- **4G:** Docker deploy, browser checks, integrity re-check, docs.

### Results (Phase 4 complete, awaiting review)
Details: [PHASE4_PRICE_INTELLIGENCE.md](PHASE4_PRICE_INTELLIGENCE.md).

**Test-first record**
1. `test_pricing.py` failed first (no `pricing` module), then passed: 16.
2. `test_phase4_api.py` and `test_phase4_edge_cases.py`: 13 failed first (missing fields and routes; the integrity test passed trivially), then all passed.
3. The stale-summary test failed first (`ensure_summaries_current` missing), then passed.
4. Frontend: 5 test files failed to load first (missing `compareSelection`), then 2 assertions in new tests were corrected.
   - One expected a label exactly once although it legitimately appears twice.
   - One expected an error before the user attempted the action.
5. Two Phase 3 product-page assertions were updated on purpose, because the Phase 4 brief changes the wording:
   - The lowest-price badges are now the three named measures.
   - Unknown shipping reads "Unknown". "Total incomplete" is kept per CLAUDE.md.
   - The history message is the brief's new text.

**Final counts**
- Backend `pytest`: **156 passed**, 0 failed, 0 skipped (125 before Phase 4 + 31 new).
- Frontend `vitest`: **60 passed** in 8 files (37 before + 23 new).
- `npm run build` (typecheck + build): passes.

**Database integrity** (counts and MongoDB `dbHash`, before and after Phase 4)
- All 8 source collections in Imported, Demo and Live are identical to the Phase 4 baseline above, as is `marketlens_accounts` (1 user, 1 session).
- Still 44 contradiction flags, 0 observations with `observed_at`, 1,500 observations.
- Only `product_summaries` changed: rebuilt to version 2 (500 documents in Imported).
- No `mltest_*` databases are left over.
- The sample CSV's checksum is unchanged.

**Docker:** api, worker, frontend and mongo all healthy after rebuild. The worker log shows "Rebuilt 500 product summaries in imported (read model was out of date)".

**Browser verification** (running app, Imported mode)
- **Verified:**
  - Explorer: MCL0001 card shows "From ₹1,370" and "Lowest confirmed delivered ₹1,430". The compare tray fills with 2 products. The delivered-price sort works (₹510, ₹520, ₹520, ₹530).
  - Compare page for MCL0001 vs MCL0222: three price rows, discount ranges, MCL0222's stock contradiction, and the sub-category comparability warning. Remove updates the URL.
  - MCL0222 details: all 9 sections; 5 charts with Table toggle; discount table; conditional offers "not included in any total"; contradiction callout; quality labels; history message; offer details expand.
  - Light and dark themes: every checked text element is ≥ 6.59:1 contrast (AA requires 4.5).
  - At 1440, 1024, 768 and 375 px: no page-level horizontal scroll and text ≥ 12 px. Two mobile overflows were found and fixed: tray chips, and the comparison table widening the layout viewport.
  - All compare requests returned 200.
- **Not verified by hand:** screen-reader output, keyboard-only use in a real browser (component tests cover keyboard reachability), the reduced-motion setting.

## Demo product photos
- **What changed:** Demo products now show real, openly licensed stock photos of similar products.
  - 9 photos from Wikimedia Commons (about 1.17 MB), stored locally and credited: CC0, CC BY 2.0/4.0, CC BY-SA 3.0/4.0.
  - Every category except phones; each product uses one of its category's photos.
  - Generated map: `frontend/src/lib/demoPhotos.ts`, from `python -m marketlens_core.demo.photos`. Credits: `docs/IMAGE_CREDITS.md` and `frontend/public/demo-photos/credits.json` (with checksums).
- **Display:** captioned as similar products with author and licence links; the SVG artwork is the fallback.
- **Tests:** 2 backend tests and 1 new frontend test; 2 frontend tests updated.
- **Browser:** Explorer shows the photos with no broken or external requests; the kurta crop keeps heads out of view.

## Example dataset v2
- **File:** `data/share/marketlens-demo-dataset-v2.zip` (1.8 MB, 54 files, rebuilds byte-identically). It replaces v1.
- **What changed:** the import-ready CSVs now have an `image_url` column (`/demo-images/<product_id>.svg`), so products show their artwork while browsing after import.
- **Verified:** checksums and manifest; no answer key or user data; the 279-row sample imported 279/279 into a throwaway database, all with displayable images.

## Imported product images
- **What changed:** a dataset's `image_url` column now shows the product's image while browsing (Explorer grid and table, product page, comparison).
  - The API sends a URL only when it's safe (`shared/marketlens_core/images.py`: https, real host, no credentials, ≤ 2,048 characters, host allowed by `IMAGE_HOSTS`, default `*`).
  - The UI loads it without a referrer, with the local generic image as fallback.
- **Existing Imported data:** its `placehold.co` URLs now display as images.
- **Tests:** 3 backend tests and 3 frontend tests.
- **Browser check:** an Imported Explorer card and product page load the dataset image.

## Presentation readiness and demo reference pack (final milestone, done)
- **Forecast selection** (corrected): per forecast series only.
  - The candidate is used when it beats the last-price baseline by 5%+ in that listing's own backtest; other series never influence it.
  - A short-lived workspace-wide gate was removed, and its derived cache was dropped.
  - On Demo the candidate is used for 0 / 3 / 9 of 39 series at 7 / 14 / 30 days; all others use the baseline.
- **Interval wording:** "Nominal 80%" is shown separately from measured coverage. Any horizon below 80% says "Not calibrated", and the Methodology page states that coverage improved only with wider ranges.
  - Updated numbers are in [FORECAST_EVALUATION.md](FORECAST_EVALUATION.md).
- **Demo artwork:** 40 fictional SVG product illustrations plus a fallback, in `frontend/public/demo-images/`, generated by `marketlens_core.demo.artwork`.
  - Local, with no external references; labelled "demo artwork"; shown only in Demo mode.
  - They appear on the Overview ("Featured demo products"), Explorer grid and table, product detail, comparison and watchlist. Imported keeps the generic placeholder.
- **Demo reference pack** (`data/demo-reference/`, built by `python -m marketlens_core.demo.reference`):
  - Contents: README, schema, manifest with checksums, CSVs (40 products, 92 offers, 17,100 observations, 326 reviews), 41 images, and `answer-key/README.md` (the key itself is excluded).
  - Deterministic: the generated-at time is the Demo generation run's time.
- **Guide:** [PRESENTATION_GUIDE.md](PRESENTATION_GUIDE.md), a 6:30 click-by-click script.
- **Verification:** see the final report. Core `dbHash` and the answer key unchanged. Browser: Overview, Explorer, DEMO-P-001 Evidence / Timeline / Forecast, Analyst, Admin (sign-in screen), Methodology at 375 px, with no overflow, no text under 12 px and no broken or external images; light and dark themes.

## Methodology and forecast calibration (roadmap step 7, done, awaiting review)
- **Methodology page** (`/methodology`; nav and Home links already pointed there):
  - 12 sections, each covering what it does, inputs, formulas and thresholds, missing data, meaning, and limitations.
  - Includes the data-mode note, the cutoff explanation, and a "not proof of misconduct" disclaimer.
  - Every number comes from `GET /api/v1/methodology`, which reads the constants from the modules (`shared/marketlens_core/methodology.py`). The page can't drift from the code, and a test feeds unusual values to prove it.
- **Interval calibration** (`forecast-2`): split-conformal on relative absolute errors, rank ⌈(n+1)·0.8⌉, walk-forward. Each origin uses only errors whose target day was already observed; no range with fewer than 10 errors.
  - The candidate-vs-baseline rule is unchanged.
  - The previous method is still measured for comparison.
  - The forecast tab shows the average width and says when no range is available.
- **Evaluation report:** `GET /api/v1/forecast-evaluation`, a table on the Methodology page, and [FORECAST_EVALUATION.md](FORECAST_EVALUATION.md).
  - Demo (synthetic): 39 listings; about 4,600 points per horizon.
  - Coverage before → after: 75.7 → 78.9% (7 days), 65.7 → 75.8% (14), 51.4 → 70.8% (30).
  - Width before → after: 3.42 → 3.73%, 4.29 → 4.74%, 4.54 → 6.21%.
  - Still below 80%, reported as such.
  - Baseline MAE is lower than the candidate's at every horizon.
- **Verification:** see the final report. Core `dbHash`, the Demo answer key (sha256 1369340e…), user rules, notifications, watchlist and summaries are unchanged.
  - The account's one session expired through its TTL index between milestones; no code removed it, and the account is unchanged.

## Analyst dashboard and remaining alert types (roadmap step 6, done, awaiting review)
- **Dashboard** (`shared/marketlens_core/dashboard.py`; `GET /api/v1/dashboard/meta`, `GET /api/v1/dashboard?cutoff=…Z&window=30|90|180&category=&marketplace=`; page `/analyst`).
  - **Data:** products, listings, verified vs snapshot observations, quarantined rows, stock contradictions (Imported: 44, preserved), discount mismatches, unknown shipping, synthetic labels.
  - **Stores:** listings, and how often each had the lowest current price.
  - **Analytics** (verified history up to the cutoff only): Real Price Detector, advice, score bands, real-savings distribution, price-index trend, audit findings by rule (linked to products), sync pair results and pattern products, forecast backtest MAE/MAPE vs baseline with measured coverage ("nominal 80%").
  - **Product table:** links to each product's Evidence tab.
  - **Cost and cache:** it reuses the product services (at most 200 products per request). Results are cached in the derived `dashboard_cache` collection, keyed by parameters, method versions and the latest ingestion run, so any import changes the key. Demo: about 6 s uncached, instant cached.
- **Alert types** (`shared/marketlens_core/alerts/signals.py`). All SCOPE types are now implemented; none is unavailable.
  - **Observation-based:** below target (existing), new low, restock.
  - **State-based:** meaningful discount (crossing; minimum score 40–100), advice change, seller switch, new audit finding, new synchronization pattern.
  - **When they run:** only when an import inserts verified observations ingested after the rule became active. Snapshot-only imports never evaluate them. The cutoff is the latest verified observation time, never ingestion time.
  - **No retrospective or repeat alerts:** state-based types record a baseline first. An unchanged result is never a new event.
  - **Idempotent:** one evaluation record per (rule, run); notification id = hash(rule, analysis version, state change, cutoff); retries are safe. Email stays a local outbox record.
  - **UI:** alert-type selector in the alert dialog; rule list shows type and score; signal notifications show message, analysis version, cutoff and a "View the evidence" link.
- **Changed test:** the Phase 5 rule-validation case `new_low → "not available yet"` is now `price_prophecy → "unknown alert type"`, because new_low is implemented.
- **Verification:** see the final report. Core `dbHash` unchanged; user rules, notifications, watchlist, the account and its session unchanged. New derived collection: `dashboard_cache` (one entry per workspace after checks).
- **Next:** methodology page and final model evaluation (forecast recalibration), or the women's file once its conflicts are decided.

## Seller synchronization and pricing audit (roadmap step 5, done, awaiting review)
- **Seller synchronization** (`shared/marketlens_core/sync.py`, `GET /api/v1/products/{id}/sync?cutoff=…Z&window=`):
  - Every pair of a product's store listings is compared (seller, listing, store and currency kept separate).
  - A change is a ≥ 3% move between consecutive observed days at most 2 days apart; changes match in the same direction within ±1 day.
  - A pattern needs ≥ 3 matches covering ≥ 60% of the smaller set of changes. Statuses: pattern worth investigating, occasional, independent, no price changes, insufficient, not comparable.
  - Always "not proof", with ordinary explanations.
- **Audit** (`shared/marketlens_core/audit.py`, `GET /api/v1/products/{id}/audit?cutoff=…Z&window=`):
  - Five rules with version, kind, severity, confidence, supporting observations, ordinary explanations and limitations:
    - unsupported discount (calculated);
    - reference price raised (calculated);
    - repeated urgency while stock stayed normal (heuristic);
    - stock/availability contradiction (observed);
    - discount arithmetic (observed).
  - Rules lacking data are disabled. Snapshot observations are counted only if ingested by the cutoff.
- **UI:** "Pricing practices audit" and "Seller synchronization" sections on the product page. They include a pair list, an aligned change timeline (matched ▲▼ marks with links), a matched-changes table and a rules table, plus insufficient, error and no-finding states.
- **Answer key** (tests only): inflated reference → reference raised (high) + unsupported discount; repeated urgency → flagged; genuine discount and stable prices → no reference or urgency flag; mixed events → sync pattern on every pair; stable → no changes; seller switch → not a pattern; insufficient history → insufficient.
- **Observation:** almost every Demo product gets "unsupported discount", because the generator sets the reference (MRP) about 30% above the usual price. That's a real property of the data, and the finding lists the MRP explanation.
- **Forecast wording:** the range is now labelled "Nominal 80%", with a "Not calibrated" warning when measured coverage is more than 5 points below. Measured coverage from the last evaluation: 75.6% / 66.0% / 52.1% (7/14/30 days). Recalibration is deferred to final model evaluation.
- **Next:** analyst dashboard and alert types that depend on these signals (SCOPE §5), or the women's file once its conflicts are decided.

## Forecasting and Future Price Memory (roadmap step 4, done, awaiting review)
- **Advice fix (test-first):** Buy now only for real savings ≥ 5%. An ordinary price (including an inflated reference) is now "Consider waiting", low confidence, "not a bargain". Demo inflated-reference and stable-price products now show that.
- **Forecasting** (`shared/marketlens_core/forecast.py`, `GET /api/v1/products/{id}/forecast?cutoff=…Z&basis=`):
  - Per store listing. Daily lowest usable verified price up to the cutoff.
  - Models: baseline = last observed price; candidate = median of the last 14 observed days.
  - Rolling-origin backtest in date order for 7/14/30 days (up to 120 origins, at least 20); MAE and MAPE reported.
  - The model is used only if its MAE is ≥ 5% lower than the baseline's, otherwise the baseline. 80% range from backtest errors, with walk-forward measured coverage.
  - Unavailable for snapshot-only, under-14-day, stale (> 7 days), mixed-currency or unknown-shipping (delivered) cases.
- **Future Price Memory** (SCOPE §5, past events, not forecasts):
  - A drop is ≥ 10% below the previous 14-day median. Outcomes counted at 1/3/7/14 days: returned, stayed low or fell further.
  - Only completed outcomes count, episodes never overlap, and results are shown as counts, not probabilities.
  - It matches all 4 planted mixed-event outcomes in the answer key (checked in test code only).
- **Demo walk-forward results** (39 products with history, cutoff 31 Oct 2026; mean per product):

  | Horizon | MAE baseline | MAE median | MAPE baseline | MAPE median | Median chosen | Measured coverage of the 80% range |
  | --- | --- | --- | --- | --- | --- | --- |
  | 7 days | ₹60.10 | ₹74.13 | 1.15% | 1.51% | 0 | 75.6% |
  | 14 days | ₹82.02 | ₹91.25 | 1.66% | 1.94% | 3 | 66.0% |
  | 30 days | ₹112.54 | ₹117.33 | 2.33% | 2.36% | 9 | 52.1% |

  The baseline usually wins, so it's used. Measured coverage is below the nominal 80%; it's shown as measured.
- **UI:**
  - Forecast tab: horizon selector, chart (observed solid, estimate dashed amber with range, hover and arrow-key readout), estimate labelled "Forecast, not observed", backtest table vs baseline, method, Future Price Memory table, limitations.
  - Buying advice shows a separate forecast-based expectation only when the model beat the baseline. It never changes the recommendation.
- **Verification:** see the final report. `dbHash` unchanged across all databases. Browser: dark, light and 375 px.
- **Next:** seller synchronization and dark-pattern audit rules (SCOPE §5), or importing the women's file once its conflicts are decided.

## Buying advice (roadmap step 3, done, awaiting review)
- **Prerequisites checked:**
  - SCOPE's Buying advice line doesn't require forecasting, so no forecast was built. Every response says advice is based on observed prices, not predicted ones.
  - The answer key's `*_change_pct` (negative = drop) and the detector's savings (positive = drop) are consistent; no change needed.
- **Backend** (`shared/marketlens_core/advice.py`): `GET /api/v1/products/{id}/advice?mode=&cutoff=…Z&window=&basis=`.
  - Built on the evidence analysis at an explicit UTC cutoff; recommends Buy now, Consider waiting or Insufficient evidence.
  - Each response gives reasons, disagreeing signals, confidence with reasons, current vs usual price, score, coverage, freshness, limitations and provenance.
  - It cross-checks the other price basis.
- **UI:** a Buying advice card under the overview (green / warm / grey). It shares the date, window and basis with Evidence, and links to Evidence and the Time Machine. It has loading, error and insufficient states.
- **Demo results** (cutoff 31 Oct 2026):
  - Genuine discount: Buy now, high confidence.
  - Inflated reference: Buy now, low confidence, with reference-increase and advertised-not-supported signals.
  - Shipping offset: Buy now, low confidence, delivered price disagrees.
  - Insufficient history: Insufficient evidence.
  - Imported MCL0001: Insufficient evidence.
- **Verification:**
  - Backend 241 passed (+11), frontend 91 passed (+5), build passes; Docker services healthy.
  - `dbHash` of Imported, Demo, Live and accounts identical before and after.
  - Browser: light and dark themes; 375 px without overflow, text ≥ 12 px.
- **Ops note:** rebuilding only `api` leaves nginx holding the old container address (502) until `frontend` restarts. Rebuild all services together, or restart `frontend`.
- **Next:** Forecasting (SCOPE §5: 7/14/30-day horizons, chronological backtests against a baseline). Advice can then cite a validated forecast.

## Evidence: Real Price Detector and Genuine Discount Score (roadmap step 2, done, awaiting review)
- **Backend** (`shared/marketlens_core/evidence.py`): `GET /api/v1/products/{id}/evidence?mode=&cutoff=…Z&window=30|90|180&basis=base|delivered`.
  - Explicit UTC cutoff (422 otherwise); verified observations only; nothing after the cutoff is read.
  - Per store listing: usual price = median of daily lowest prices, current observation excluded; savings % per SCOPE; reference-price increase finding; advertised discount kept separate.
  - Score 0–100 (60/25/15); unavailable under 14 distinct observed days; missing components disclosed.
  - Response carries result, evidence (daily prices, dates, store, current observation), provenance, window, cutoff, exclusions and limitations.
- **Evidence tab:** verdict, score meter with component breakdown, advertised-vs-observed ladder, reference-increase callout, evidence table, per-listing table, limitations, tooltips, loading/error/insufficient states. Shares the cutoff date (`at`) with the Time Machine and links each evidence date to it.
- **Answer-key evaluation** (test code only, `tests/test_evidence_answer_key.py`, cutoff 31 Oct 2026, 90-day window): genuine discount 19.07% below usual (key −20%), score 68; inflated reference: savings 0%, reference +50.44% flagged, advertised not supported, score 11; stable prices 0%; shipping offset 9.1% on base, 0% delivered; insufficient history unavailable; sparse days disclosed. All 7 pass.
- **Verification:** backend 230 passed (212 + 18); frontend 86 passed (80 + 6); build passes; deployed. `dbHash` of Imported, Demo, Live and accounts identical before and after. Browser: Demo genuine, inflated and insufficient products; 375 px without overflow, text ≥ 12 px; Time Machine link works.
- **Next:** Buying advice (Buy now / Consider waiting / Insufficient evidence) using these signals.

## History foundation (roadmap step 1, done, awaiting review)
- **A. Demo generator** (`shared/marketlens_core/demo/generator.py`): seed 20261031, end date 31 Oct 2026, 184 days.
  - **Catalogue:** 40 fictional products in 8 categories (brands; size, storage or colour), 92 listings, 17,100 UTC observations, 326 reviews (3 products have none).
  - **Scenarios:** 10 planted types.
  - **Pipeline:** the rows go through the normal import pipeline with the strict UTC rule (0 rejected).
  - **Export:** `data/demo-export/demo_dataset.csv`, plus a separate `answer_key.json`. The key is never stored in a database; a test checks no analytics code references it.
  - **Admin:** Data administration → Demo data (generate; reset requires typing RESET DEMO). Worker jobs; Demo database only.
- **B. History service** (`shared/marketlens_core/history.py`): `GET /api/v1/products/{id}/history?cutoff=…Z&window=7|30|90|180&basis=` and `/as-of?at=…Z`.
  - An explicit UTC cutoff is required (422 otherwise), and nothing after it is read.
  - Only `history_eligible` observations count; timezone-unknown snapshots are counted as excluded. Gaps are never filled, and unknown shipping is a gap.
  - The as-of view returns no "next" observation.
- **C. History import:**
  - Optional `review_id`, `review_date`, `reviewer_name` and `storage` fields. A supplied review ID is the review's identity, so repeated rows give one review.
  - A DATA_REQUIREMENTS #1–#9 report on every import using the history rule (wizard evaluation `history_check`).
  - Women's file dry run (throwaway database): 61 reviews, R2/R3/R5/R6/R8 pass. **60 rows are quarantined as `immutable_conflict`**: base_listing and price_history rows share a listing and UTC time but disagree on price and other fields. **Not imported.**
- **D. UI:**
  - Price History section: purple area chart of verified data only, presets in the URL, base or confirmed delivered price, gaps, data table, HTML axis labels (≥ 12 px).
  - Restored Timeline / Evidence / Forecast tabs (`?tab=`). The Time Machine has date picker, scrubber, play/pause, previous/next (never past the latest observation), compare date and "Changed" markers. Evidence and Forecast show honest not-yet states.
- **E. Verification:**
  - Backend 212 passed (196 + 16). Frontend 80 passed (74 + 6). Build passes.
  - `dbHash`: Imported, Live and accounts identical; only Demo changed (by the approved generation).
  - Browser: Demo chart, presets, tabs and Time Machine; 375 px without overflow.
- **Open decisions for the women's file:** which of each conflicting base/history pair is authoritative (or keep the quarantine); the "Amazon India" label; no answer key.
- **Next roadmap step:** Evidence (Real Price Detector, Genuine Discount Score), scored against `answer_key.json`.

## Roadmap review after Phase 5 (6 Nov 2026)
The project documents define no phases. The requirements status, dependencies and a recommended order (awaiting the owner's confirmation) are in [ROADMAP_REVIEW.md](ROADMAP_REVIEW.md). The baseline was re-verified read-only: unchanged; 196 backend and 74 frontend tests passing.

## Phase 5: Watchlists, price alerts and notifications (done, awaiting review)

Details: [PHASE5_WATCHLISTS_ALERTS.md](PHASE5_WATCHLISTS_ALERTS.md).

**Results**
- Tests: backend **196 passed** (156 + 40 new), frontend **74 passed** (60 + 14 new); build passes.
- Test-first: every new group failed first (missing modules or routes). Three of my own new expectations were corrected:
  - "Mark all read" only applies to notifications that haven't been dismissed.
  - The edit input shows "₹1,400" through the shared money formatter, per CLAUDE.md.
  - A Phase 3 product-page assertion was updated for the new wording.
- Docker: all four services healthy.
- **Real databases:** identical to the Phase 5 baseline by count and `dbHash`, accounts included. The five new collections exist in each workspace and are empty. No test data was ever written there.

**End-to-end** (disposable stack `docker compose -p mle2e`, own MongoDB volume, removed afterwards)
- Through the API:
  - An alert on the existing snapshot created 0 notifications.
  - One new UTC observation (₹1,300 ≤ ₹1,350) created exactly 1.
  - Requeuing the job and re-importing the same file created no duplicate.
  - Another user saw 0.
- In the browser:
  - The signed-out Watch tap resumed after sign-in.
  - Creating an alert: invalid target refused; ₹1,400 saved; 0 unread.
  - Edit (₹1,350, Flipkart, delivered), pause and resume.
  - Escape closes the dialog and returns focus.
  - A new qualifying observation (₹1,280 + ₹60 = ₹1,340) showed "Alerts, 1 unread" and the rule "Waiting to re-arm". Mark as read set it to 0.
- Layout and themes:
  - 1440, 1024, 768 and 375 px: no page-level horizontal scroll, text ≥ 12 px, and the dialog fits.
  - **Fixed:** the Notifications header overflowed at 375 px.
  - **Fixed:** nginx let browsers keep a stale `index.html` after deploys. It now sends `no-cache` for pages and `immutable` for hashed assets, with security headers kept.
  - Contrast AA in both themes (lowest 6.59:1 light, 7.76:1 dark).
- **Not verified by hand:** screen-reader output, the reduced-motion setting.

## Phase 5 plan (original)

## Phase 5 plan (original)

### Scope alignment (SCOPE.md §5 is authoritative)
SCOPE §5: "Watchlists and alerts: target price, notes, horizon, alert rules (below target, new low, meaningful discount, advice change, seller switch, restock, audit finding, synchronization anomaly), cooldowns, de-duplication, re-arm, read/unread, pause and delete. Delivery is in-app. Email is a local outbox stating nothing was sent. A signed-out Track price tap resumes after sign-in; adding an existing product merges settings."

- **Built in Phase 5:**
  - Watchlist with notes and a watch-until date (the "horizon"). Re-adding merges settings.
  - **Below-target** rules (base or confirmed delivered price, optional store) with cooldown, de-duplication, re-arm, pause (disable) and delete (archive).
  - In-app notifications with read/unread and dismiss.
  - A local email outbox that records "not sent" for every notification.
  - A signed-out Track price / Watch tap resumes after sign-in.
- **Deferred, each needing data or analytics that don't exist yet:**
  - **New low and restock:** need verified chronological (UTC) observations.
  - **Meaningful discount:** needs the Genuine Discount Score (14+ verified days).
  - **Advice change:** needs Buying advice.
  - **Seller switch:** needs repeated seller-level history.
  - **Audit finding:** needs audit rules.
  - **Synchronization anomaly:** needs seller-synchronization analytics.
  The API rejects these types with a plain reason.
- The brief adds nothing SCOPE forbids. The brief's "no external delivery" matches SCOPE's local outbox.

### Baseline (read-only, before Phase 5)
- Identical to the end of Phase 4: same counts and `dbHash` for all 8 source collections in Imported, Demo and Live; `product_summaries` 500 (version 2); 44 flags; all observations `timezone_unknown`.
- `marketlens_accounts`: 1 user (admin) and 1 session.
- Tests: 156 backend and 60 frontend passing.

### Checklist
- [ ] 5B Watchlist: model, unique per user/workspace/product, PUT-merge, DELETE idempotent, ownership, workspace.
- [ ] 5C Rules: validation (basis, store, currency, positive integer minor units, type), auto-watchlist, current snapshot shown as context only, edit / disable / enable / archive.
- [ ] 5D Engine: evaluates only observations inserted by a later ingestion run; unique event key per rule and observation; re-arm and cooldown; crash-safe order; alert jobs after import; stale-job requeue.
- [ ] 5E UI: Watch toggle (cards, product page), Watchlist & alerts page, alert dialog, notification centre, unread bell, sign-in resume.
- [ ] 5F End-to-end in isolated databases only; responsive, themes, accessibility.
- [ ] 5G Regression, integrity, docs.

### Known limitations
- No verified price history exists, so the history area is an empty state. No charts are derived from snapshots.
- No brand, size or colour data, so these aren't compared.
- No currency picker for mixed-currency data (the API never compares currencies).
- Name search is an unanchored match (fine at 500 products).
