# Roadmap and requirements review (after Phase 5)

Read-only review dated 6 Nov 2026. Nothing was implemented, imported or changed in any database.

## 1. Is there a documented roadmap?
**No.** CLAUDE.md, SCOPE.md, DATA_REQUIREMENTS.md and DESIGN.md contain no phases, milestones or ordering. SCOPE.md is a feature specification.
- The "Phase 2–5" numbering came from the instructions given at the start of each phase. PROGRESS.md records that history; it doesn't define a roadmap.
- So the documentation can't name an "exact next phase". The order recommended below is derived from SCOPE's own dependencies. **It needs the project owner's confirmation** before it's treated as the roadmap.

## 2. Verified baseline (6 Nov 2026, read-only)
- **Imported:** 500 products, 1,500 offers, 1,500 observations, 1,500 reviews; same `dbHash` as at the end of Phase 5.
  - 44 contradiction flags.
  - All observations `timezone_unknown`; **0 are history-eligible**.
  - `product_summaries` 500 (version 2).
  - Ingestion runs 5, rejected records 12,715, source files 5, jobs 4: all kept.
- **Demo and Live:** 0 documents in every collection.
- **Phase 5 collections** (watchlists, alerts, events, notifications, outbox): 0 in every workspace.
- **Accounts:** 1 user (admin) and 1 session, untouched.
- **Tests:** backend 196 passed, frontend 74 passed, production build passes. All four Docker services healthy.

## 3. SCOPE.md requirements: status
**Legend:**
- **Done:** built and tested.
- **Partial:** some of it is built.
- **Missing:** not started.
- **Blocked:** needs verified history or other data first.

| SCOPE item | Status | Notes |
| --- | --- | --- |
| §2 Roles (consumer, analyst, admin), ownership | Partial | Roles, sessions and ownership done. No analyst screens. |
| §3 Data modes, separate databases, badge | Done | Live stays disabled (no provider), as designed. |
| §3 Labels carried into exports | Missing | No exports exist yet. |
| §3 Results labelled observed / calculated / estimated / forecast / simulated | Partial | Observed and calculated labels exist; estimated, forecast and simulated have no features yet. |
| §4 Data model, money, unknown shipping, first dataset | Done | |
| §5 Import wizard (CSV/JSON/JSONL), quarantine, append | Done | Gaps for history files with repeated review rows: see §5 below. |
| §5 Product explorer | Done | Brand filter has no data in the men's file (the women's file has brands). |
| §5 Product page: breadcrumb, prices, store rows | Done | |
| §5 Product page: Buying advice card | Missing / Blocked | Needs analytics (history). |
| §5 Product page: price-history chart 7/30/90/180 | Blocked | Needs verified history. The empty state is in place. |
| §5 Product page: three tabs (Timeline, Evidence, Forecast) | **Missing (regression)** | Phase 3 had placeholder tabs; the Phase 4 restructure removed them. They must be restored. |
| §5 Real Price Detector | Blocked | Needs a daily price window. |
| §5 Genuine Discount Score | Blocked | Needs ≥ 14 distinct observed days. |
| §5 Time Machine | Blocked | Needs observations with verified time. |
| §5 Seller synchronization | Blocked | Needs repeated seller-level observations. |
| §5 Future Price Memory | Blocked | Needs completed 1/3/7/14-day outcomes. |
| §5 Forecasting | Blocked | Needs enough history for backtests. |
| §5 Buying advice | Blocked | Built on the analytics above. |
| §5 Audit rules (dark patterns) | Blocked | Mostly needs repeated observations. Rules lacking required fields must be disabled. |
| §5 Comparison (up to 4) | Done | |
| §5 Watchlist: target, notes, horizon, below-target alerts, cooldown, de-dup, re-arm, pause, delete, read/unread, in-app, outbox, signed-out resume, merge | Done | |
| §5 Alert types: new low, restock, meaningful discount, advice change, seller switch, audit finding, sync anomaly | Blocked | Each depends on history or analytics. |
| §5 Data administration: runs, rejected records | Done | |
| §5 Data administration: job status, provider status, Demo-only reset | Partial / Missing | Import job status shown; no provider status panel; no Demo reset. |
| §5 Analyst dashboard | Missing | |
| §5 Demo data generator (30–50 products, 180+ days, scenarios, separate answer key, CSV export) | **Missing** | This is the project's own source of verified history for Demo. See §4. |
| §6 Customer reviews | Done | |
| §7 Design, themes, 12 px, contrast, responsive, keyboard, reduced motion, data tables | Done | Checked in Phases 3–5. |
| §7 Glossary and Methodology | Missing | The Methodology page is a placeholder. |
| §7 Offline, stale-data and insufficient-history states | Partial | Insufficient-history and error states exist; no offline or stale-data states. |
| §8 Rate limits | Partial | Only a sign-in throttle. |
| §8 URL allowlist | Missing | External images are never loaded; no allowlist mechanism yet. |
| §8 End-to-end and accessibility test suites | Partial | Real-database integration and component tests exist. No automated browser end-to-end or accessibility suite (checks were run by hand). |
| §8 Test that price display is identical everywhere | Partial | One shared formatter; no explicit cross-screen test. |

## 4. Dependencies and verified history
**Nearly every remaining requirement needs verified, timezone-aware history.** The men's snapshot can never provide it: one observation per listing, no timezone.

| Feature | Minimum history it needs |
| --- | --- |
| Price-history chart and presets | Daily verified observations, up to 180 days |
| Real Price Detector | Daily comparable prices over the window, excluding the current one |
| Genuine Discount Score | ≥ 14 distinct observed days, or it reads "unavailable" |
| Time Machine | Observations with verified UTC time |
| Future Price Memory | Past events with completed 1/3/7/14-day outcomes and no overlap |
| Forecasting | Enough history for chronological backtests, with 7/14/30-day horizons |
| Seller synchronization, seller switch alert | Repeated seller-level observations |
| New low, restock alerts | Chronologically ordered observations |
| Meaningful discount / advice change alerts | The Genuine Discount Score and Buying advice |

Three possible sources of verified history:
1. **Demo data generator (SCOPE §5).**
   - Explicitly required by SCOPE: deterministic, 180+ days, planted scenarios with a separate answer key, Demo database only, every value synthetic.
   - It is *documented synthetic Demo data*, not fabricated evidence. It never touches Imported, and the answer key lets analytics be **tested** against known truth.
   - No external dependency, so it can start immediately.
2. **`data/samples/womens_clothing_all_in_one.csv`** (already in the repository; checked read-only).
   - **Meets most of the history rules:** 12,715 rows (61 base listings + 12,654 history rows), 20 products, 61 listings with mostly 181 or 361 observations each. 180 distinct days (10 May to 5 Nov 2026), every timestamp UTC, all synthetic, no stock contradictions, no future rows, 4 sellers each observed 91–4,268 times. It also has real `brand`, `size` and `colour` columns.
   - **Why the earlier import quarantined every row:** the category "Women's Clothing" wasn't mapped to a launch category. That was correct behaviour, not a data fault.
   - **Problems to resolve before it can be imported correctly:**
     - Review fields are repeated on every row (61 distinct `review_id`s, each up to 361 times). The importer currently derives review identity per observation, so it would create about 12,715 copies of 61 reviews. It must use the file's `review_id`.
     - It has `review_date` and `reviewer_name`, which SCOPE §6 allows to be shown "only if the data has them". The importer doesn't map them yet.
     - It uses the store label "Amazon India" where the men's file uses "Amazon". Labels must not be merged silently; a decision is needed.
     - **No separate answer key** (DATA_REQUIREMENTS #9). Analytics can run on it but can't be scored.
     - Its product IDs don't overlap the men's file. It's a separate catalogue with its own base listings, not the history file for the men's base file.
3. **History for the men's catalogue (DATA_REQUIREMENTS).** Not delivered. Until it is, the men's products correctly stay "history unavailable".

## 5. Email outbox and external delivery
- The local outbox is **intentional**. SCOPE §5 says "Delivery is in-app. Email is a local outbox stating nothing was sent."
- External email, SMS or push appears **nowhere** in SCOPE. Under CLAUDE.md ("Do not add features outside CLAUDE.md or docs/SCOPE.md. Ask first") it would need explicit approval and a real provider.
- Delivery is already separated from evaluation (`alerts/delivery.py`), so it can be added later without changing alert logic.

## 6. Recommended order (needs confirmation)
1. **Next: verified history foundation.** This unblocks everything else.
   - **A.** Demo data generator, Demo-only reset, CSV export, separate answer key (SCOPE §5).
   - **B.** Importer readiness for history files, plus a DATA_REQUIREMENTS acceptance report. Then, *only with the owner's authorization*, import the women's file into Imported.
   - **C.** Cutoff-aware history service, price-history chart (7/30/90/180), restored Timeline / Evidence / Forecast tabs, and the Time Machine in the Timeline tab.
2. **Evidence:** Real Price Detector, Genuine Discount Score, Evidence tab. Scored against the Demo answer key.
3. **Forecast and advice:** Future Price Memory, forecasting with backtests and baseline fallback, Buying advice card and Forecast tab, advice-change and meaningful-discount alerts.
4. **Seller and audit analytics:** seller synchronization, audit rules, Analyst dashboard, and the remaining alert types (new low, restock, seller switch, audit finding, sync anomaly).
5. **Hardening:**
   - API rate limits, URL allowlist, exports carrying the data-mode label
   - glossary and Methodology page, offline and stale-data states
   - automated browser end-to-end and accessibility suites, and a cross-screen price-display test

## 7. Test-first plan for the recommended next phase: "Verified history foundation"

### 7A. Demo data generator (SCOPE §5)
- **Functionality**
  - A deterministic generator with a fixed seed, run as a worker job. It writes **only** to `marketlens_demo`.
  - **Catalogue:** 30–50 fictional products across several launch categories, with fictional brands and category-appropriate variants (size for clothing, storage for phones, and so on). Every value is `synthetic`.
  - **Observations:** 180+ days of daily UTC observations (`history_eligible`). Seller IDs stay consistent; some products have several sellers; a few have several observations per day from several sellers.
  - **Reviews:** 3–15 plain-text "Synthetic sample review" reviews per product, plus some products with none.
  - **Scenarios:** genuine discount, inflated reference price, repeated urgency, shipping increase offsetting a price drop, seller switch, market-wide movement, mixed outcomes, stable prices, sparse or missing days, insufficient history.
  - **Answer key:** written to a **separate file** (`data/demo-export/answer_key.json`). Analytics code never reads it.
  - **CSV export** to `data/demo-export/`.
  - **Reset:** admin only, explicit confirmation, Demo database only. It removes Demo marketplace data and Demo-workspace watchlists, alerts and notifications. Accounts are never touched.
- **API (admin only)**
  - `POST /api/v1/admin/demo/generate`: queues the job.
  - `GET /api/v1/admin/demo/status`: last run, counts, export paths.
  - `POST /api/v1/admin/demo/reset`: queues the reset.
- **Screen:** a Data administration "Demo data" panel: generate, reset with typed confirmation, status, counts, export location.
- **Tests first**
  - The same seed produces byte-identical output (hash of the exported CSVs).
  - Counts fall within the SCOPE ranges.
  - Every document is `synthetic`; every observation is UTC and history-eligible.
  - Every planted scenario appears in the answer key and in the data.
  - A static check that no analytics module references the answer-key path.
  - Imported, Live and accounts fingerprints are unchanged after generate and reset.
  - Reset clears only Demo.
  - Non-admin requests get 403, signed-out requests 401.

### 7B. History-file readiness and acceptance report
- **Functionality**
  - Use the file's own review identity when a `review_id` column exists, so repeated review rows de-duplicate.
  - Optional mapping for `review_date` and `reviewer_name`, and for multi-record files (`record_type`).
  - Keep `brand`, `size` and `colour` when supplied (the mapping already exists).
  - Map extra attributes such as `fabric` into raw only; never guess.
  - **Acceptance report** for files imported with the history rule, checking DATA_REQUIREMENTS #1–#9: ID consistency with stored listings, ≥ 180 days of coverage, UTC on every row, required fields, synthetic flag, stock consistency (already quarantined), repeated seller observations, no future rows, answer key present or absent.
  - The report is shown in the import wizard. It describes the file; it doesn't change it.
- **API:** `GET /api/v1/admin/imports/{id}/history-check`.
- **Tests first** (using small purpose-built files and the women's file *in throwaway databases only*)
  - 12,715 rows produce 61 reviews, not 12,715.
  - Review dates are kept; reviewer names are shown only if present.
  - Each failing requirement is reported with a plain reason; a file without an answer key is flagged.
  - Re-import adds nothing.
  - Snapshot observations remain unchanged.
- **Owner decisions needed before importing the women's file into Imported:**
  - category mapping ("Women's Clothing" → `womens-clothing`)
  - the "Amazon India" store label
  - accepting a file without an answer key

### 7C. History service, chart, tabs, Time Machine
- **Functionality**
  - A shared history service. Every call takes an explicit **cutoff** and never reads observations after it (CLAUDE.md).
  - Daily series per listing or product: base or delivered price, store filter.
  - Gaps are shown as gaps, never filled in. Observations with an unknown timezone are excluded and the exclusion is stated. Coverage statistics are returned.
  - Time Machine: the observed state at a requested time (the latest verified observation at or before it per listing), with actual observation time, age, previous and next observation, and changed fields.
  - Product page: restore the three tabs (`?tab=timeline|evidence|forecast`).
    - The price-history chart (purple area, 7/30/90/180 presets in the URL, data-table view, theme-aware) is drawn only from verified observations.
    - Timeline holds the Time Machine: date picker, scrubber, play/pause, previous/next, side-by-side comparison.
    - Evidence and Forecast show plain "arrives in a later phase" or "insufficient history" states until those phases.
- **API**
  - `GET /api/v1/products/{id}/history?mode=&cutoff=&window=7|30|90|180&basis=&marketplace=`
  - `GET /api/v1/products/{id}/as-of?mode=&at=`
- **Tests first**
  - Cutoff never leaks later data (property-style checks over random cutoffs).
  - Window and preset boundaries; gaps not interpolated; timezone-unknown excluded with a reason.
  - Imported men's products still say "history unavailable".
  - As-of picks the right observation, with the right age and changed fields.
  - Tabs and presets survive refresh and Back.
  - Chart table view; empty and insufficient states.
  - No chart drawn from snapshots.
  - Layout at 1440, 1024, 768 and 375 px, and themes.

### Acceptance criteria for the phase
- The Demo generator is deterministic, Demo-only and synthetic-labelled, with a separate answer key and CSV export. Reset touches only Demo.
- History-file import de-duplicates repeated reviews and produces a DATA_REQUIREMENTS acceptance report. Nothing is imported into Imported without the owner's authorization.
- History, as-of, the chart and Timeline use only verified UTC observations with an explicit cutoff. No fabricated points, trends, highs, lows or forecasts.
- The three product tabs are restored.
- All earlier tests still pass. Imported source collections, accounts and user data are unchanged (by `dbHash`), unless an authorized import is run.
- Documentation is updated.
