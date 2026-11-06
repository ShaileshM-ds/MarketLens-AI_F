# Phase 5: Watchlists, price alerts and notifications

## What users can do
- **Watch** a product from a product card or product page. Signed out, the tap opens sign-in and completes afterwards (SCOPE §5).
- **Watchlist & alerts** (`/watchlist`):
  - **Watched products:** shows the lowest listed price, lowest confirmed delivered price, snapshot availability, quality labels and alert status. Remove a product with a confirm step; its alerts are archived.
  - **Price alerts:** create, edit, pause and resume, re-arm, delete (with confirmation). Shows the last evaluation and last notification.
  - **Notifications:** current, unread or all (including dismissed). Mark as read, mark all as read, dismiss.
- **Set price alert** on a product page opens the same dialog.
- The bell in the top bar shows the unread count for the current workspace.
- The page states that alerts are checked when new observations are imported, with no continuous live monitoring.

## Scope versus SCOPE.md §5
- **Built:**
  - Target price (below-target rules), notes, horizon (watch-until date).
  - Cooldowns, de-duplication, re-arm, pause and delete, read/unread.
  - In-app delivery, and an email local outbox stating nothing was sent.
  - The signed-out Track price tap resumes after sign-in; re-adding a product merges settings.
- **Deferred:** new low, restock, meaningful discount, advice change, seller switch, audit finding, synchronization anomaly. Each needs verified history or analytics that don't exist yet. The API refuses them with the reason.

## Data model (per workspace database; never crosses Demo / Imported / Live)
| Collection | Contents | Key indexes |
| --- | --- | --- |
| `watchlist_items` | user_id, product_id, notes (≤500, plain text), horizon_date, added_at, updated_at | unique (user_id, product_id); (user_id, added_at) |
| `alert_rules` | user_id, mode, product_id, type `below_target`, marketplace (or any), basis `base` or `delivered`, target_price_minor, currency, cooldown_hours (0–720), enabled, armed, status `active` or `archived`, active_since, last_evaluated, last_triggered_at | (user_id, status, created_at); (product_id, status, enabled) |
| `alert_events` | one per evaluated (rule, observation): outcome, reason, value, target, notification_id | _id = event key; (rule_id, evaluated_at) |
| `notifications` | owner, product, store, listing, observation_id, ingestion_run_id, basis, observed and target minor units, currency, source time and quality, synthetic and source label, read_at, dismissed_at | _id = event key; (user_id, dismissed_at, created_at); (user_id, read_at) |
| `email_outbox` | status `not_sent`, "nothing was sent" note | unique notification_id |

Users and sessions stay in `marketlens_accounts`.

## Evaluation semantics
1. **When:** after an import job has durably stored its observations, the worker runs a separate `alerts` job for that ingestion run (`jobs._id = alerts|<run_id>`).
2. **Which observations:** only those inserted by that run (`provenance.ingestion_run_id`).
   - Duplicates are never inserted and quarantined rows never become observations, so neither is evaluated.
3. **Which rules:** active, enabled rules for the observation's product, and the rule's store if it has one.
   - Only if the observation's ingestion time is later than the rule's `active_since` (creation or last resume).
   - Existing snapshots, and observations imported while a rule was paused, are therefore never replayed. They're shown only as "context only" when an alert is created.
4. **Exclusions** (recorded as `excluded` with a reason, never notified), checked in this order:
   - the watch period has ended
   - different currency
   - stock contradiction
   - reported out of stock
   - availability not reported
   - no price
   - unknown shipping, for delivered-price rules
5. **Comparison:** value ≤ target, in exact integer minor units. The value is the base price, or base price plus *known* shipping.
6. **Outcomes:**
   - `notified`
   - `suppressed_not_armed`: the rule already notified, and no observation above target has arrived since
   - `suppressed_cooldown`: within `cooldown_hours` of the last notification
   - `not_qualifying`: above target; this also re-arms a disarmed rule
   - `excluded`
7. **Order within a run:** verified `observed_at` first, then source timestamp, then ID. This is a stable processing order, not market chronology.
8. **Wording:** notifications always read "New qualifying observation detected". They never say "price dropped", because a drop would need two verified, chronologically comparable observations.

## Idempotency and reliability
- **Event key:** sha256(rule_id|observation_id)[:24]. It's the `_id` of both the event and the notification.
- **Processing order:**
  1. If the event already exists, skip.
  2. If the notification exists, a crash happened after notifying: record the outcome as notified.
  3. Otherwise insert the notification (a duplicate `_id` is ignored), record the email outbox entry, update the rule, then insert the event.
- **Guarantee:** at most one notification per (rule, observation). This is not "exactly once".
- **Recovery:** at startup the worker requeues alert jobs left `running` or `failed` for more than 10 minutes, at most 5 attempts.
- **Transactions:** standalone MongoDB has no multi-document transactions; the order above makes retries safe.
- **Batching:** runs are evaluated in batches of 500 observations, with rules fetched per batch by product.

## API (signed-in users; every route takes `mode`; other users' records return 404)
| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/watchlist` | Your watched products with pricing, availability, quality labels and alert counts |
| `PUT /api/v1/watchlist/{product_id}` | Add, or merge `notes` / `horizon_date` |
| `DELETE /api/v1/watchlist/{product_id}` | Remove (idempotent); archives that product's alerts |
| `GET /api/v1/alerts[?include_archived=true]` | Your alert rules |
| `POST /api/v1/alerts` | Create (`product_id`, `marketplace?`, `basis`, `target_price_minor`, `currency`, `cooldown_hours`, `enabled`). Returns `current_context` |
| `PATCH /api/v1/alerts/{id}` | Edit, `enabled`, `rearm` |
| `DELETE /api/v1/alerts/{id}` | Archive; history is kept |
| `GET /api/v1/alerts/{id}/events` | Evaluation log |
| `GET /api/v1/notifications?status=active\|unread\|all&page=&page_size≤100` | List, with total and unread |
| `GET /api/v1/notifications/unread-count` | Unread count |
| `GET /api/v1/notifications/{id}` | Detail, with the triggering observation and its rule |
| `POST /api/v1/notifications/{id}/read`, `/{id}/dismiss`, `/read-all` | State changes; dismissing never deletes |

Validation errors are 422 with a plain reason: unsupported type, basis, currency or store; a target that isn't a positive integer; a cooldown outside 0–720. Live returns 409 (no provider). Signed-out requests return 401. Cross-site writes are blocked (403).

## Verification
- Backend: 196 tests (40 Phase 5), including real-MongoDB engine tests for every rule above. Frontend: 74 tests (14 Phase 5).
- End-to-end tests ran in a disposable copy of the stack (`docker compose -p mle2e`, its own MongoDB volume, since removed). No test data was ever written to the user's databases. Browser checks:
  - The signed-out Watch tap resumed after sign-in.
  - Creating an alert through the dialog: invalid input refused; ₹1,400 saved; no retrospective notification.
  - Edit (target, store, basis), pause and resume.
  - Escape closes the dialog and returns focus.
  - One new qualifying observation gave exactly 1 notification (bell "1 unread"); mark as read set it to 0.
  - Through the API: requeue and re-import created no duplicate, and another user saw nothing.
- Layout: no page-level horizontal scroll, and text ≥ 12px, at 1440, 1024, 768 and 375 px on the Watchlist page (with the dialog open), product page and explorer. A 375 px overflow in the Notifications header was found and fixed.
- Contrast: AA in both themes (lowest 6.59:1 light, 7.76:1 dark).

## Limitations
- Accounts are created with the CLI; there's no self sign-up.
- Alerts depend on new imports; there's no live provider and no scheduled ingestion.
- Seven SCOPE alert types are deferred (above).
- There's no external email or push delivery. The outbox records "not sent", as SCOPE requires.
- Not verified by hand: screen-reader announcements and the reduced-motion setting.
