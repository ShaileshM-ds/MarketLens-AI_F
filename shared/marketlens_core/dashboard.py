"""Analyst dashboard (SCOPE §5): summaries and tables built from the active workspace only.

- Every historical figure takes an explicit UTC cutoff: verified observations after it are never read.
  Timezone-unknown snapshot observations count only if ingested by the cutoff, and are reported separately;
  they never enter historical analytics.
- Per-product analytics reuse the evidence, advice, audit, synchronization and forecast services, so the
  dashboard can never disagree with a product page. At most MAX_PRODUCTS products are analysed per request
  (stated in the response when truncated).
- Results are cached in `dashboard_cache` (derived, deletable) under a key of the parameters, method versions
  and the workspace's latest ingestion run. Any new import or Demo regeneration changes the key, so stale
  results are never served; old entries are pruned.
"""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from pymongo.database import Database

from .advice import ADVICE_VERSION, buying_advice
from .audit import AUDIT_VERSION, product_audit
from .db import INGESTION_RUNS, OBSERVATIONS, OFFERS, PRODUCTS, REJECTED_RECORDS
from .evidence import EVIDENCE_VERSION, _median
from .forecast import FORECAST_VERSION, HORIZONS, product_forecast
from .history import UTC, WINDOWS, HistoryError, _aware, _iso, product_history, require_utc
from .sync import SYNC_VERSION, product_sync

DASHBOARD_VERSION = "dashboard-1"
DASHBOARD_CACHE = "dashboard_cache"
MAX_PRODUCTS = 200
CACHE_KEEP = 100
SAVINGS_BINS = [(-1e9, -10, "≤ −10%"), (-10, -5, "−10 to −5%"), (-5, 5, "−5 to +5%"), (5, 10, "5 to 10%"), (10, 20, "10 to 20%"), (20, 1e9, "≥ 20%")]


def dashboard_meta(db: Database) -> dict:
    last = db[OBSERVATIONS].find_one({"history_eligible": True}, {"observed_at": 1}, sort=[("observed_at", -1)])
    return {"latest_verified_at": _iso(_aware(last["observed_at"])) if last else None,
            "categories": sorted(c for c in db[PRODUCTS].distinct("category") if c),
            "marketplaces": sorted(m for m in db[OFFERS].distinct("marketplace") if m),
            "windows": [w for w in WINDOWS if w >= 30]}


def _cache_key(db: Database, params: dict) -> str:
    run = db[INGESTION_RUNS].find_one({}, {"_id": 1}, sort=[("created_at", -1), ("_id", -1)])
    versions = [DASHBOARD_VERSION, EVIDENCE_VERSION, ADVICE_VERSION, AUDIT_VERSION, SYNC_VERSION, FORECAST_VERSION]
    raw = json.dumps({**params, "run": run and run["_id"], "runs": db[INGESTION_RUNS].estimated_document_count(), "v": versions}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def dashboard(db: Database, *, cutoff: datetime, window_days: int = 90, category: str | None = None,
              marketplace: str | None = None, now: datetime | None = None) -> dict:
    cutoff = require_utc(cutoff, "cutoff")
    if window_days not in WINDOWS or window_days < 30:
        raise HistoryError("window must be 30, 90 or 180 days.")
    params = {"cutoff": _iso(cutoff), "window": window_days, "category": category, "marketplace": marketplace}
    key = _cache_key(db, params)
    hit = db[DASHBOARD_CACHE].find_one({"_id": key})
    if hit:
        return {**hit["payload"], "cache": {"hit": True, "computed_at": _iso(_aware(hit["created_at"]))}}
    now = now or datetime.now(timezone.utc)
    payload = _compute(db, cutoff, window_days, category, marketplace)
    payload["params"] = params
    db[DASHBOARD_CACHE].replace_one({"_id": key}, {"_id": key, "payload": payload, "created_at": now}, upsert=True)
    old = [d["_id"] for d in db[DASHBOARD_CACHE].find({}, {"_id": 1}).sort("created_at", -1).skip(CACHE_KEEP)]
    if old:
        db[DASHBOARD_CACHE].delete_many({"_id": {"$in": old}})
    return {**payload, "cache": {"hit": False, "computed_at": _iso(now)}}


def _compute(db: Database, cutoff: datetime, window_days: int, category: str | None, marketplace: str | None) -> dict:
    pq: dict = {}
    if category:
        pq["category"] = category
    if marketplace:
        pq["_id"] = {"$in": db[OFFERS].distinct("product_id", {"marketplace": marketplace})}
    products = {p["_id"]: p for p in db[PRODUCTS].find(pq, {"name": 1, "category": 1, "synthetic": 1}).sort("_id", 1)}
    pids = list(products)
    oq = {"product_id": {"$in": pids}, **({"marketplace": marketplace} if marketplace else {})}
    seen = {"$or": [{"history_eligible": True, "observed_at": {"$lte": cutoff}},
                    {"history_eligible": {"$ne": True}, "provenance.ingested_at": {"$lte": cutoff}}]}
    rows = list(db[OBSERVATIONS].aggregate([
        {"$match": {**oq, **seen}},
        {"$group": {"_id": {"m": "$marketplace", "v": {"$eq": ["$history_eligible", True]}}, "n": {"$sum": 1},
                    "synthetic": {"$sum": {"$cond": ["$synthetic", 1, 0]}},
                    "contradiction": {"$sum": {"$cond": [{"$in": ["stock_availability_contradiction", {"$ifNull": ["$flags", []]}]}, 1, 0]}},
                    "mismatch": {"$sum": {"$cond": [{"$in": ["discount_mismatch", {"$ifNull": ["$flags", []]}]}, 1, 0]}},
                    "ship_unknown": {"$sum": {"$cond": [{"$eq": ["$shipping_known", True]}, 0, 1]}},
                    "labels": {"$addToSet": "$source_label"}}},
    ]))
    listings = Counter(o["marketplace"] for o in db[OFFERS].find(oq, {"marketplace": 1}))
    by_m: dict = defaultdict(lambda: {"listings": 0, "verified_observations": 0, "snapshot_observations": 0, "lowest_current_price_products": 0})
    for m, n in listings.items():
        by_m[m]["listings"] = n
    tot = Counter()
    labels = set()
    for r in rows:
        k = "verified_observations" if r["_id"]["v"] else "snapshot_observations"
        by_m[r["_id"]["m"]][k] += r["n"]
        tot[k] += r["n"]
        for f in ("synthetic", "contradiction", "mismatch", "ship_unknown"):
            tot[f] += r[f]
        labels |= {x for x in r["labels"] if x}
    observations = tot["verified_observations"] + tot["snapshot_observations"]
    out = {
        "version": DASHBOARD_VERSION, "cutoff": _iso(cutoff), "window": {"days": window_days},
        "totals": {"products": len(pids), "listings": sum(listings.values()), "verified_observations": tot["verified_observations"],
                   "snapshot_observations": tot["snapshot_observations"], "rejected_records": db[REJECTED_RECORDS].estimated_document_count(),
                   "ingestion_runs": db[INGESTION_RUNS].count_documents({"created_at": {"$lte": cutoff}})},
        "quality": {"stock_contradiction_observations": tot["contradiction"], "discount_mismatch_observations": tot["mismatch"],
                    "unknown_shipping_observations": tot["ship_unknown"], "timezone_unknown_observations": tot["snapshot_observations"],
                    "note": "Snapshot observations without a timezone are counted here but never used in historical analysis. "
                            "Rejected records are quarantined rows across all imports."},
        "provenance": {"synthetic": observations > 0 and tot["synthetic"] == observations, "synthetic_observations": tot["synthetic"],
                       "source_labels": sorted(labels)},
        "marketplaces": [],
    }
    verified_pids = sorted(db[OBSERVATIONS].distinct("product_id", {"product_id": {"$in": pids}, "history_eligible": True, "observed_at": {"$lte": cutoff}}))
    if not verified_pids:
        out["historical"] = {"status": "no_verified_history", "products": [], "products_analyzed": 0, "products_insufficient": 0,
                             "reason": "No verified UTC observations up to this cutoff, so no historical analytics are shown. Snapshot data is summarised above."}
    else:
        out["historical"] = _historical(db, products, verified_pids, cutoff, window_days, by_m)
    out["marketplaces"] = [{"marketplace": m, **v} for m, v in sorted(by_m.items())]
    return out


def _historical(db, products, pids, cutoff, window_days, by_m) -> dict:
    truncated = len(pids) > MAX_PRODUCTS
    pids = pids[:MAX_PRODUCTS]
    rows, detector, bands, advice, sav_bins = [], Counter(), Counter(), Counter(), Counter()
    audit_rules: dict = {}
    disabled = Counter()
    sync_status, pattern_products = Counter(), []
    fc = {h: {"available": 0, "chosen": Counter(), "mae_b": [], "mae_m": [], "mape_b": [], "mape_m": [], "cov": []} for h in HORIZONS}
    index_by_day: dict = defaultdict(list)
    for pid in pids:
        p = products[pid]
        a = buying_advice(db, pid, cutoff=cutoff, window_days=window_days, basis="base")
        e_status = a["evidence_status"]
        price = a["price"] or {}
        row = {"product_id": pid, "name": p.get("name"), "category": p.get("category"), "status": e_status,
               "verdict": price.get("verdict"), "savings_percent": price.get("savings_percent"),
               "score": a["score"]["value"], "band": a["score"]["band"], "advice": a["recommendation"]["code"],
               "advice_confidence": (a["confidence"] or {}).get("level"),
               "lowest_marketplace": (a["headline"] or {}).get("marketplace"), "audit": [], "sync_patterns": 0, "forecast_7": None}
        advice[a["recommendation"]["code"]] += 1
        if e_status == "available":
            detector[price["verdict"]] += 1
            bands[a["score"]["band"]] += 1
            s = price["savings_percent"]
            sav_bins[next(lbl for lo, hi, lbl in SAVINGS_BINS if lo <= s < hi)] += 1
            if row["lowest_marketplace"] in by_m:
                by_m[row["lowest_marketplace"]]["lowest_current_price_products"] += 1
        au = product_audit(db, pid, cutoff=cutoff, window_days=window_days)
        for f in au["findings"]:
            r = audit_rules.setdefault(f["rule_id"], {"title": f["title"], "kind": f["kind"], "count": 0, "products": []})
            r["count"] += 1
            r["products"].append({"product_id": pid, "name": p.get("name"), "severity": f["severity"]})
            row["audit"].append(f["rule_id"])
        for r in au["rules"]:
            disabled[r["rule_id"]] += r["status"] == "disabled"
        sy = product_sync(db, pid, cutoff=cutoff, window_days=window_days)
        for pr in sy["pairs"]:
            sync_status[pr["status"]] += 1
        row["sync_patterns"] = sum(pr["status"] == "pattern" for pr in sy["pairs"])
        if row["sync_patterns"]:
            pattern_products.append({"product_id": pid, "name": p.get("name"), "pairs": row["sync_patterns"]})
        f = product_forecast(db, pid, cutoff=cutoff, basis="base")
        for hz in (f or {}).get("horizons", []):
            if hz["status"] != "available":
                continue
            m = {x["key"]: x for x in hz["models"]}
            c = fc[hz["days"]]
            c["available"] += 1
            c["chosen"][hz["chosen"]] += 1
            c["mae_b"].append(m["naive"]["mae_minor"])
            c["mae_m"].append(m["recent_median"]["mae_minor"])
            c["mape_b"].append(m["naive"]["mape_percent"])
            c["mape_m"].append(m["recent_median"]["mape_percent"])
            if hz["forecast"]["interval"]["measured_coverage_percent"] is not None:
                c["cov"].append(hz["forecast"]["interval"]["measured_coverage_percent"])
            if hz["days"] == 7:
                row["forecast_7"] = {"chosen": hz["chosen"], "improvement_percent": hz["improvement_percent"]}
        h = product_history(db, pid, cutoff=cutoff, window_days=window_days, basis="base")
        vals = [pt["value_minor"] for pt in (h or {}).get("series", [])]
        if len(vals) >= 2:
            med = _median(vals)
            for pt in h["series"]:
                index_by_day[pt["date"]].append(Decimal(pt["value_minor"]) / med * 100)
        rows.append(row)

    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None  # noqa: E731
    horizons = []
    for hd, c in fc.items():
        cov = mean(c["cov"])
        horizons.append({"days": hd, "available": c["available"], "model_chosen": c["chosen"].get("recent_median", 0),
                         "baseline_chosen": c["chosen"].get("naive", 0), "mean_mae_baseline_minor": mean(c["mae_b"]),
                         "mean_mae_model_minor": mean(c["mae_m"]), "mean_mape_baseline_percent": mean(c["mape_b"]),
                         "mean_mape_model_percent": mean(c["mape_m"]), "mean_measured_coverage_percent": cov,
                         "coverage_note": (f"Nominal 80% range; measured coverage {cov}%"
                                           + (" — not calibrated." if cov is not None and cov < 75 else ".")) if cov is not None else "Nominal 80% range; coverage not measured."})
    trend = [{"date": d, "index": float(_median_dec(v)), "products": len(v)} for d, v in sorted(index_by_day.items())]
    return {
        "status": "available", "truncated": truncated, "max_products": MAX_PRODUCTS,
        "products_analyzed": sum(r["status"] == "available" for r in rows),
        "products_insufficient": sum(r["status"] != "available" for r in rows),
        "detector": dict(detector), "score_bands": dict(bands), "advice": dict(advice),
        "savings_distribution": [{"label": lbl, "count": sav_bins.get(lbl, 0)} for _, _, lbl in SAVINGS_BINS],
        "audit": {"by_rule": audit_rules, "disabled": dict(disabled),
                  "note": "Evidence-based flags for review, not legal findings or accusations."},
        "sync": {"pairs": dict(sync_status), "pattern_products": pattern_products,
                 "note": "Patterns worth investigating, not proof of collusion."},
        "forecast": {"horizons": horizons, "note": "Forecasts are estimates, tested against a last-price baseline. Ranges are nominal; see measured coverage."},
        "trend": trend,
        "trend_note": "Daily median across products of each product's lowest verified price as a % of its own median in the window (100 = usual).",
        "products": rows,
    }


def _median_dec(v: list) -> Decimal:
    s = sorted(v)
    n = len(s)
    m = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return m.quantize(Decimal("0.01"))
