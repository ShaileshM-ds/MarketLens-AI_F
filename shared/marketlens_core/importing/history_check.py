"""DATA_REQUIREMENTS.md #1-#9 report for files imported with the strict history rule.

It describes the file and the evaluation; it never changes either. `ready` is false when any check fails.
"""

from collections import defaultdict

from .config import ImportConfig

MIN_DAYS = 180
FULL_FIELDS = ("original_price", "shipping_cost", "stock_quantity", "availability", "seller_name")


def _check(cid: str, requirement: str, status: str, detail: str) -> dict:
    return {"id": cid, "requirement": requirement, "status": status, "detail": detail}


def history_check(ev, config: ImportConfig) -> dict:
    kept = [o.result for o in ev.outcomes if o.status != "rejected"]
    rejected = [o.result for o in ev.outcomes if o.status == "rejected"]

    def rejected_with(code: str, predicate=lambda m: True) -> int:
        return sum(1 for r in rejected if any(i.code == code and predicate(i.message) for i in r.reasons))

    days = {r.observation["observed_at"].date() for r in kept if r.observation.get("observed_at")}
    seller_days = defaultdict(set)
    for r in kept:
        if r.observation.get("observed_at"):
            seller_days[r.observation["seller_id"]].add(r.observation["observed_at"].date())
    min_seller_days = min((len(v) for v in seller_days.values()), default=0)
    conflicts = rejected_with("listing_identity_conflict")
    no_utc = rejected_with("invalid_timestamp", lambda m: m.startswith("timestamp") and "future" not in m)
    future = rejected_with("invalid_timestamp", lambda m: "future" in m)
    unmapped = [f for f in FULL_FIELDS if not config.field_map.get(f)]
    blanks = sum(1 for r in kept if any(r.raw.get(config.field_map[f], "").strip() == "" for f in FULL_FIELDS if config.field_map.get(f)))
    contradictions = rejected_with("stock_availability_contradiction")
    non_synthetic = sum(1 for r in kept if not r.observation.get("synthetic"))

    checks = [
        _check("R1", "Same product, seller and listing IDs as stored data", "fail" if conflicts else "pass",
               f"{conflicts} row(s) try to move a stored listing to another product or seller; {len(ev.new_listing_ids)} listing(s) are new to this workspace."),
        _check("R2", f"At least {MIN_DAYS} days of daily observations", "pass" if len(days) >= MIN_DAYS else "fail",
               f"Found {len(days)} distinct UTC day(s); at least {MIN_DAYS} required."),
        _check("R3", "ISO 8601 UTC timestamp on every row", "fail" if no_utc else "pass", f"{no_utc} row(s) without a valid UTC timestamp were quarantined."),
        _check("R4", "Full observation fields", "fail" if unmapped else ("pass" if not blanks else "info"),
               f"Unmapped: {', '.join(unmapped)}." if unmapped else f"{blanks} row(s) leave at least one of these blank (kept as unknown): {', '.join(FULL_FIELDS)}."),
        _check("R5", "Every row flagged synthetic", "pass" if kept and not non_synthetic else "fail", f"{non_synthetic} accepted row(s) are not marked synthetic."),
        _check("R6", "Stock and availability consistent", "fail" if contradictions else "pass", f"{contradictions} contradictory row(s) quarantined, unchanged."),
        _check("R7", "Each seller observed repeatedly", "pass" if seller_days and min_seller_days >= 2 else "fail",
               f"{len(seller_days)} seller(s); the least-observed seller appears on {min_seller_days} day(s)."),
        _check("R8", "No future-dated rows", "fail" if future else "pass", f"{future} future-dated row(s) quarantined."),
        _check("R9", "Separate answer key", "info", "Can't be checked from the data file. Supply the answer key as a separate file; it is never imported or read by analytics."),
    ]
    return {"ready": not any(c["status"] == "fail" for c in checks), "checks": checks}
