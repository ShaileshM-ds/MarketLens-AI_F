# Data requirements: history dataset

A history dataset will be delivered later. It must meet every requirement below before it is imported. A file that fails any of them is rejected or quarantined with a plain reason; it is never silently fixed.

1. **Same identifiers.** Uses the same `product_id`, `seller_id` and `listing_id` as the base file. No new or renamed IDs for existing listings.
2. **Length.** At least 180 days of daily observations.
3. **Timestamps.** Every row has an ISO 8601 UTC timestamp (for example `2026-05-01T09:30:00Z`).
4. **Full observation fields.** Each row carries the full set of observation fields used by the base file (price, MRP/reference price, shipping, stock, availability, seller, etc.). Unknown values are left blank, never filled in.
5. **Synthetic flag.** Every row is flagged synthetic.
6. **Stock / availability consistency.** Stock and availability agree on every row (for example, no "Out of Stock" with stock above zero).
7. **Repeated seller observations.** Each seller is observed repeatedly across the period, so seller-level patterns can be analysed.
8. **No future-dated rows.** No timestamp is later than the delivery date.
9. **Separate answer key.** Any planted scenarios ship in a SEPARATE answer-key file. Analytics code never reads it; it is used only for evaluation.

Observations in this file append to the base data as new immutable records. They never overwrite earlier observations.
