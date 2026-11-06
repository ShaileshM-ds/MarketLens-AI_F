"""Seller synchronization (SCOPE §5): needs repeated seller-level offers; results are patterns worth
investigating, never proof of collusion. Version SYNC_VERSION.

For every pair of store listings of one product (seller, listing, store and currency kept separate):
- Daily value = lowest usable verified base price that day, from observations up to an explicit UTC cutoff
  inside the window. Missing days are never filled.
- A price change = a move of at least CHANGE_PERCENT between consecutive observed days at most MAX_GAP_DAYS
  apart (a longer gap is a data gap, not a change).
- Two changes match when they go in the same direction within MATCH_DAYS of each other (each change is
  matched at most once, same day first).
- Pattern worth investigating: at least MIN_MATCHES matches covering at least MIN_SHARE of the changes of the
  listing that changed less. Price similarity alone is never a finding.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations

from pymongo.database import Database

from .db import OBSERVATIONS, OFFERS, PRODUCTS
from .evidence import _unusable
from .history import UTC, WINDOWS, HistoryError, _aware, _iso, require_utc

SYNC_VERSION = "sync-1"
CHANGE_PERCENT = 3.0
MAX_GAP_DAYS = 2
MATCH_DAYS = 1
MIN_DAYS = 14
MIN_MATCHES = 3
MIN_SHARE = 0.6
STALE_DAYS = 7
NOTE = ("Similar or simultaneous price changes are patterns worth investigating, not proof of collusion. "
        "They can have ordinary causes, listed with each result.")
BENIGN = [
    "A store-wide or festival sale that both listings joined.",
    "The brand changed its list price or recommended price for every seller.",
    "Both sellers use repricing software that follows the same market prices.",
    "Common cost changes (supplier price, shipping or taxes).",
    "The same business may sell on more than one store.",
]


def _pct(a: int, b: int) -> float:
    return float(((Decimal(b) - Decimal(a)) / Decimal(a) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _changes(series: list[tuple[date, int]]) -> list[dict]:
    out = []
    for (d0, v0), (d1, v1) in zip(series, series[1:]):
        if (d1 - d0).days > MAX_GAP_DAYS or not v0:
            continue
        p = _pct(v0, v1)
        if abs(p) >= CHANGE_PERCENT:
            out.append({"date": d1.isoformat(), "from_date": d0.isoformat(), "from_minor": v0, "to_minor": v1, "change_percent": p})
    return out


def _match(ca: list[dict], cb: list[dict]) -> list[dict]:
    used, out = set(), []
    for offset_pass in range(MATCH_DAYS + 1):  # same day first, then 1 day apart
        for a in ca:
            if any(m["date_a"] == a["date"] for m in out):
                continue
            da = date.fromisoformat(a["date"])
            for j, b in enumerate(cb):
                if j in used or (a["change_percent"] > 0) != (b["change_percent"] > 0):
                    continue
                if abs((date.fromisoformat(b["date"]) - da).days) == offset_pass:
                    used.add(j)
                    out.append({"date_a": a["date"], "date_b": b["date"], "change_a_percent": a["change_percent"],
                                "change_b_percent": b["change_percent"], "days_apart": (date.fromisoformat(b["date"]) - da).days})
                    break
    return sorted(out, key=lambda m: m["date_a"])


def product_sync(db: Database, product_id: str, *, cutoff: datetime, window_days: int = 90) -> dict | None:
    cutoff = require_utc(cutoff, "cutoff")
    if window_days not in WINDOWS:
        raise HistoryError(f"window must be one of {', '.join(map(str, WINDOWS))} days.")
    product = db[PRODUCTS].find_one({"_id": product_id}, {"synthetic": 1})
    if not product:
        return None
    start = datetime.combine(cutoff.date() - timedelta(days=window_days - 1), time.min, UTC)
    offers = list(db[OFFERS].find({"product_id": product_id}).sort("_id", 1))
    rows = db[OBSERVATIONS].find({"product_id": product_id, "history_eligible": True, "observed_at": {"$gte": start, "$lte": cutoff}},
                                 {"raw": 0, "content_hash": 0}).sort([("observed_at", 1), ("_id", 1)])
    days: dict[str, dict[date, list[int]]] = defaultdict(lambda: defaultdict(list))
    currencies: dict[str, set] = defaultdict(set)
    synthetic, labels = [], set()
    for o in rows:
        synthetic.append(bool(o.get("synthetic")))
        if o.get("source_label"):
            labels.add(o["source_label"])
        if _unusable(o, "base"):
            continue
        days[o["listing_id"]][_aware(o["observed_at"]).date()].append(o["price_minor"])
        currencies[o["listing_id"]].add(o.get("currency"))
    listings = {}
    for off in offers:
        series = [(d, min(v)) for d, v in sorted(days[off["_id"]].items())]
        last = series[-1][0] if series else None
        listings[off["_id"]] = {
            "listing_id": off["_id"], "seller_id": off.get("seller_id"), "seller_name": off.get("seller_name"), "marketplace": off.get("marketplace"),
            "currency": next(iter(currencies[off["_id"]])) if len(currencies[off["_id"]]) == 1 else None,
            "mixed_currency": len(currencies[off["_id"]]) > 1, "observed_days": len(series),
            "last_date": last.isoformat() if last else None, "stale": last is None or (cutoff.date() - last).days > STALE_DAYS,
            "changes": _changes(series), "_dates": {d for d, _ in series},
        }
    out = {"product_id": product_id, "cutoff": _iso(cutoff), "window": {"days": window_days, "start": _iso(start), "end": _iso(cutoff)},
           "method": {"version": SYNC_VERSION, "change_percent": CHANGE_PERCENT, "max_gap_days": MAX_GAP_DAYS, "match_days": MATCH_DAYS,
                      "min_days": MIN_DAYS, "min_matches": MIN_MATCHES, "min_share": MIN_SHARE, "stale_days": STALE_DAYS, "basis": "base"},
           "note": NOTE, "status": "insufficient", "reason": None, "pairs": [],
           "source": {"synthetic": all(synthetic) if synthetic else bool(product.get("synthetic")), "source_labels": sorted(labels)}}
    if len(offers) < 2:
        out["reason"] = "Synchronization needs at least two store listings of the product."
        return out
    for la, lb in combinations([listings[o["_id"]] for o in offers], 2):
        out["pairs"].append(_pair(la, lb))
    for l in listings.values():
        l.pop("_dates")
    usable = [p for p in out["pairs"] if p["status"] not in ("insufficient", "not_comparable")]
    if usable:
        out["status"] = "available"
    else:
        out["reason"] = ("Insufficient evidence: no pair of store listings has repeated, current, verified observations in the same currency "
                         f"(at least {MIN_DAYS} common observed days within {STALE_DAYS} days of the cutoff).")
    order = {"pattern": 0, "occasional": 1, "independent": 2, "no_changes": 3, "insufficient": 4, "not_comparable": 5}
    out["pairs"].sort(key=lambda p: (order[p["status"]], -p["matched"], p["a"]["listing_id"], p["b"]["listing_id"]))
    return out


def _pair(la: dict, lb: dict) -> dict:
    pub = lambda l: {k: v for k, v in l.items() if k != "_dates"}  # noqa: E731
    common = len(la["_dates"] & lb["_dates"])
    p = {"a": pub(la), "b": pub(lb), "common_days": common, "matched": 0, "same_day": 0, "a_first": 0, "b_first": 0,
         "match_share": None, "matches": [], "status": "insufficient", "label": "Insufficient evidence", "summary": "", "benign_explanations": BENIGN}
    if la["mixed_currency"] or lb["mixed_currency"] or (la["currency"] and lb["currency"] and la["currency"] != lb["currency"]):
        return {**p, "status": "not_comparable", "label": "Not comparable",
                "summary": "Different currencies: these listings' prices are never compared."}
    if la["stale"] or lb["stale"]:
        return {**p, "summary": f"Insufficient evidence: a listing has no usable verified observation in the last {STALE_DAYS} days before the cutoff."}
    if common < MIN_DAYS:
        return {**p, "summary": f"Insufficient evidence: only {common} days observed for both listings (at least {MIN_DAYS} needed)."}
    ca, cb = la["changes"], lb["changes"]
    if not ca and not cb:
        return {**p, "status": "no_changes", "label": "No price changes",
                "summary": f"Insufficient evidence of synchronization: neither listing changed price by {CHANGE_PERCENT:g}% or more. "
                           "Similar or equal prices alone are not synchronization."}
    matches = _match(ca, cb)
    n = len(matches)
    share = n / min(len(ca), len(cb)) if ca and cb else 0.0
    p.update(matched=n, matches=matches, match_share=round(share, 2), same_day=sum(m["days_apart"] == 0 for m in matches),
             a_first=sum(m["days_apart"] > 0 for m in matches), b_first=sum(m["days_apart"] < 0 for m in matches))
    if n >= MIN_MATCHES and share >= MIN_SHARE:
        p.update(status="pattern", label="Synchronized changes worth investigating",
                 summary=f"{n} of {min(len(ca), len(cb))} price changes moved in the same direction within {MATCH_DAYS} day "
                         f"({p['same_day']} on the same day). This is a pattern worth investigating, not proof of coordination.")
    elif n:
        p.update(status="occasional", label="Occasional simultaneous changes",
                 summary=f"{n} matching change{'s' if n != 1 else ''} out of {len(ca)} and {len(cb)}: too few to call a pattern.")
    else:
        p.update(status="independent", label="Independent movements",
                 summary=f"{len(ca)} and {len(cb)} price changes, none in the same direction within {MATCH_DAYS} day of each other.")
    return p
