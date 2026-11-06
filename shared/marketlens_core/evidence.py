"""Real Price Detector and Genuine Discount Score (SCOPE §5). Each analysis takes an explicit UTC cutoff.

Method (version EVIDENCE_VERSION), per store listing, so every comparison is the same seller, store,
variant and currency:
- Only `history_eligible` observations (verified UTC time) between the window start and the cutoff are
  read. Nothing after the cutoff is read. Timezone-unknown snapshots are counted and excluded.
- An observation is usable when it has a price on the chosen basis (delivered needs known shipping),
  is reported in stock or limited stock, and has no stock contradiction.
- The current observation is the listing's latest verified observation at or before the cutoff. If it
  isn't usable, the listing has no result (an out-of-stock or unconfirmed price is never "current").
- Baseline = median of the daily comparable prices (lowest usable value each day) over the window, with
  the current observation excluded. Missing days are gaps, never filled.
- Historical savings % = 100 x (baseline - current) / baseline. Negative results stay visible.
- Fewer than MIN_DAYS distinct observed days: "Insufficient historical evidence"; no verdict or score.
- The product headline is the listing with the lowest current comparable price. Listings in different
  currencies are never compared.
Coupons and payment offers are conditional and never subtracted. The advertised discount and reference
price are the seller's, kept separate from the measured reduction.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pymongo.database import Database

from .db import OBSERVATIONS, OFFERS, PRODUCTS
from .explorer import availability_class
from .history import HISTORY_UNAVAILABLE, UTC, WINDOWS, BASES, HistoryError, _aware, _iso, _value, require_utc

EVIDENCE_VERSION = "evidence-1"
MIN_DAYS = 14                 # SCOPE: under 14 distinct observed days the score is unavailable
SAVINGS_THRESHOLD = 5.0       # |savings| below this is "around its usual price"
FULL_SAVINGS = 25.0           # savings at or above this earn the full savings component
AGREE_FULL, AGREE_NONE = 5.0, 25.0  # advertised minus real savings, in points: full / no agreement
REFERENCE_INCREASE = 20.0     # reference price up this much vs its baseline median is a finding
STALE_DAYS = 3
WEIGHTS = {"savings": 60, "percentile": 25, "agreement": 15}
INSUFFICIENT = "Insufficient historical evidence"
_FIELDS = {f: 1 for f in ("listing_id", "observed_at", "price_minor", "shipping_minor", "shipping_known", "currency",
                          "reference_price_minor", "advertised_discount_percent", "availability",
                          "stock_quantity", "flags", "synthetic", "source_label", "provenance.ingestion_run_id", "provenance.source_filename", "coupon_discount_minor",
                          "payment_offer")}
_C = Decimal("0.01")


def _q(d: Decimal) -> float:
    return float(d.quantize(_C, rounding=ROUND_HALF_UP))


def _int(d: Decimal) -> int:
    return int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _median(values: list[int]) -> Decimal:
    v = sorted(values)
    n = len(v)
    return Decimal(v[n // 2]) if n % 2 else (Decimal(v[n // 2 - 1]) + Decimal(v[n // 2])) / 2


def _unusable(o: dict, basis: str) -> str | None:
    if "stock_availability_contradiction" in (o.get("flags") or []):
        return "stock_contradiction"
    if o.get("price_minor") is None:
        return "no_price"
    if _value(o, basis) is None:
        return "unknown_shipping"
    if availability_class(o.get("availability")) not in ("in_stock", "limited_stock"):
        return "not_purchasable"
    return None


_REASONS = {
    "stock_contradiction": "Its latest observation has availability and stock quantity that disagree.",
    "no_price": "Its latest observation has no price.",
    "unknown_shipping": "Total incomplete: shipping is unknown at its latest observation, so a delivered price can't be confirmed.",
    "not_purchasable": "Its latest observation is reported out of stock or without availability, so it isn't a current purchasable price.",
}


def score_components(*, savings: float, percentile: float, advertised: float | None) -> dict:
    """Genuine Discount Score 0-100: 60% savings, 25% price percentile, 15% agreement with the advertised
    discount. A missing component is disclosed and the remaining weights are rescaled."""
    s = Decimal(str(savings))
    sav = max(Decimal(0), min(s, Decimal(str(FULL_SAVINGS)))) / Decimal(str(FULL_SAVINGS)) * 100
    comps = [
        {"key": "savings", "weight": WEIGHTS["savings"], "available": True, "value": _q(sav),
         "explanation": f"Real savings of {_q(s)}% against the usual price (0% or less scores 0; {FULL_SAVINGS:g}% or more scores 100)."},
        {"key": "percentile", "weight": WEIGHTS["percentile"], "available": True, "value": _q(Decimal(str(percentile))),
         "explanation": f"The current price is lower than {_q(Decimal(str(percentile)))}% of observed days in the window (ties count half)."},
    ]
    if advertised is None:
        comps.append({"key": "agreement", "weight": WEIGHTS["agreement"], "available": False, "value": None,
                      "explanation": "No advertised discount was reported, so agreement can't be scored. Its weight is left out."})
    else:
        gap = Decimal(str(advertised)) - max(s, Decimal(0))
        span = Decimal(str(AGREE_NONE - AGREE_FULL))
        agree = Decimal(100) if gap <= Decimal(str(AGREE_FULL)) else max(Decimal(0), (Decimal(str(AGREE_NONE)) - gap) / span * 100)
        comps.append({"key": "agreement", "weight": WEIGHTS["agreement"], "available": True, "value": _q(agree),
                      "explanation": f"Advertised {advertised:g}% vs real {_q(max(s, Decimal(0)))}%: within {AGREE_FULL:g} points scores 100, "
                                     f"{AGREE_NONE:g} points or more scores 0."})
    used = sum(c["weight"] for c in comps if c["available"])
    total = sum(Decimal(c["weight"]) * Decimal(str(c["value"])) for c in comps if c["available"]) / Decimal(used)
    for c in comps:
        c["points"] = _q(Decimal(c["weight"]) * Decimal(str(c["value"])) / Decimal(used)) if c["available"] else None
    value = _int(total)
    band = "strong" if value >= 70 else "moderate" if value >= 40 else "weak"
    label = {"strong": "Strong evidence of a genuine discount", "moderate": "Some evidence of a genuine discount",
             "weak": "Little evidence of a genuine discount"}[band]
    return {"status": "available", "value": value, "band": band, "label": label, "weight_used": used, "components": comps, "reason": None}


def _listing(off: dict, obs: list[dict], basis: str, cutoff: datetime) -> dict:
    out = {"listing_id": off["_id"], "marketplace": off.get("marketplace"), "seller_id": off.get("seller_id"),
           "seller_name": off.get("seller_name"), "status": "unavailable", "reason": None, "currency": None,
           "observed_days": 0, "current_minor": None, "baseline_minor": None, "savings_percent": None, "current_observed_at": None}
    excl = defaultdict(int)
    if not obs:
        return {**out, "reason": "No verified observation in the analysis window."}, excl, None
    cur = obs[-1]
    out["current_observed_at"] = _iso(cur["observed_at"])
    usable = []
    for o in obs:
        why = _unusable(o, basis)
        if why:
            excl[why] += 1
        else:
            usable.append(o)
    currencies = {o.get("currency") for o in usable}
    if len(currencies) > 1:
        return {**out, "reason": "This listing's observations use different currencies; they aren't compared."}, excl, None
    why = _unusable(cur, basis)
    if why:
        return {**out, "reason": _REASONS[why]}, excl, None
    by_day: dict[date, list[dict]] = defaultdict(list)
    for o in usable:
        if o is not cur:
            by_day[_aware(o["observed_at"]).date()].append(o)
    days = sorted(by_day)
    distinct = len(set(days) | {_aware(cur["observed_at"]).date()})
    out.update(currency=cur.get("currency"), observed_days=distinct, current_minor=_value(cur, basis))
    if distinct < MIN_DAYS or not days:
        return {**out, "status": "insufficient",
                "reason": f"{INSUFFICIENT}: {distinct} distinct observed day{'s' if distinct != 1 else ''} in the window; at least {MIN_DAYS} are needed."}, excl, None
    daily = []
    for d in days:
        low = min(by_day[d], key=lambda o: (_value(o, basis), o["_id"]))
        daily.append({"date": d.isoformat(), "value_minor": _value(low, basis), "reference_minor": low.get("reference_price_minor"),
                      "observations": len(by_day[d])})
    vals = [p["value_minor"] for p in daily]
    base = _median(vals)
    current = Decimal(out["current_minor"])
    savings = _q((base - current) / base * 100) if base else None
    out.update(status="available", baseline_minor=_int(base), savings_percent=savings)
    detail = {"cur": cur, "daily": daily, "baseline": base, "savings": savings,
              "percentile": float((Decimal(sum(v > current for v in vals)) + Decimal(sum(v == current for v in vals)) / 2) / len(vals) * 100)}
    return out, excl, detail


def _reference(cur: dict, daily: list[dict]) -> dict:
    refs = [p["reference_minor"] for p in daily if p["reference_minor"] is not None]
    cref = cur.get("reference_price_minor")
    if cref is None or not refs:
        return {"current_minor": cref, "baseline_minor": None, "change_percent": None, "increased": None, "since": None,
                "note": "The seller's reference price isn't known for enough days to compare."}
    base = _median(refs)
    change = _q((Decimal(cref) - base) / base * 100) if base else None
    increased = change is not None and change >= REFERENCE_INCREASE
    since = None
    if increased:
        level = base * (1 + Decimal(str(REFERENCE_INCREASE)) / 100)
        since = _iso_date(cur)
        for p in reversed(daily):
            if p["reference_minor"] is None or Decimal(p["reference_minor"]) < level:
                break
            since = p["date"]
    note = (f"The seller's reference price is {change}% above its usual level in this window"
            f"{f', since {since}' if since else ''}. A higher reference makes the advertised discount look larger without lowering the price."
            if increased else "The seller's reference price is close to its usual level in this window.")
    return {"current_minor": cref, "baseline_minor": _int(base), "change_percent": change, "increased": increased, "since": since, "note": note}


def _iso_date(o: dict) -> str:
    return _aware(o["observed_at"]).date().isoformat()


def _detector(d: dict, listing: dict, basis: str) -> dict:
    s = d["savings"]
    cur = d["cur"]
    adv = cur.get("advertised_discount_percent")
    verdict = "below_usual" if s >= SAVINGS_THRESHOLD else "above_usual" if s <= -SAVINGS_THRESHOLD else "around_usual"
    label = {"below_usual": "Genuine price reduction", "around_usual": "No real reduction", "above_usual": "Above its usual price"}[verdict]
    price_word = "delivered price" if basis == "delivered" else "price"
    explanation = {
        "below_usual": f"The current {price_word} is {s}% below its usual (median) level over the window.",
        "around_usual": f"The current {price_word} is within {SAVINGS_THRESHOLD:g}% of its usual (median) level ({s:+}%).",
        "above_usual": f"The current {price_word} is {abs(s)}% above its usual (median) level over the window.",
    }[verdict]
    if adv is None:
        support, support_note = "no_advertised_discount", "No advertised discount was reported."
    elif adv < SAVINGS_THRESHOLD:
        support, support_note = "no_advertised_discount", f"The advertised discount is small ({adv:g}%)."
    elif adv - max(s, 0) <= AGREE_FULL:
        support, support_note = "supported", f"The advertised {adv:g}% is consistent with the observed reduction of {s}%."
    elif s >= SAVINGS_THRESHOLD:
        support, support_note = "partly_supported", f"The price did fall ({s}%), but by less than the advertised {adv:g}%."
    else:
        support, support_note = "not_supported", f"The advertised {adv:g}% isn't supported by observed prices (real change {s:+}%)."
    return {
        "verdict": verdict, "label": label, "explanation": explanation, "currency": listing["currency"],
        "current_minor": listing["current_minor"], "baseline_minor": listing["baseline_minor"], "savings_percent": s,
        "price_percentile": _q(Decimal(str(d["percentile"]))),
        "advertised_discount_percent": adv, "advertised_support": support, "advertised_note": support_note,
        "reference": _reference(cur, d["daily"]),
    }


def price_evidence(db: Database, product_id: str, *, cutoff: datetime, window_days: int = 90, basis: str = "base") -> dict | None:
    cutoff = require_utc(cutoff, "cutoff")
    if window_days not in WINDOWS:
        raise HistoryError(f"window must be one of {', '.join(map(str, WINDOWS))} days.")
    if basis not in BASES:
        raise HistoryError("basis must be 'base' or 'delivered'.")
    product = db[PRODUCTS].find_one({"_id": product_id}, {"synthetic": 1, "source_label": 1})
    if not product:
        return None
    offers = list(db[OFFERS].find({"product_id": product_id}).sort("_id", 1))
    start = datetime.combine(cutoff.date() - timedelta(days=window_days - 1), time.min, UTC)
    tz_unknown = db[OBSERVATIONS].count_documents({"product_id": product_id, "timestamp_quality": "timezone_unknown"})
    rows = list(db[OBSERVATIONS].find({"product_id": product_id, "history_eligible": True, "observed_at": {"$gte": start, "$lte": cutoff}},
                                      _FIELDS).sort([("observed_at", 1), ("_id", 1)]))
    per = defaultdict(list)
    for o in rows:
        per[o["listing_id"]].append(o)

    listings, details, excluded = [], {}, {"timezone_unknown": tz_unknown, "unknown_shipping": 0, "not_purchasable": 0, "stock_contradiction": 0, "no_price": 0}
    for off in offers:
        res, excl, det = _listing(off, per.get(off["_id"], []), basis, cutoff)
        for k, v in excl.items():
            excluded[k] += v
        listings.append(res)
        if det:
            details[off["_id"]] = det

    out = {
        "product_id": product_id, "cutoff": _iso(cutoff), "basis": basis,
        "window": {"days": window_days, "start": _iso(start), "end": _iso(cutoff)},
        "method": {"version": EVIDENCE_VERSION, "min_days": MIN_DAYS, "savings_threshold": SAVINGS_THRESHOLD,
                   "full_savings": FULL_SAVINGS, "reference_increase": REFERENCE_INCREASE, "weights": WEIGHTS,
                   "agreement_points": [AGREE_FULL, AGREE_NONE]},
        "excluded": excluded, "listings": listings,
        "source": {"synthetic": all(o.get("synthetic") for o in rows) if rows else bool(product.get("synthetic")),
                   "source_labels": sorted({o.get("source_label") for o in rows if o.get("source_label")}),
                   "ingestion_runs": sorted({(o.get("provenance") or {}).get("ingestion_run_id") for o in rows} - {None}),
                   "source_files": sorted({(o.get("provenance") or {}).get("source_filename") for o in rows} - {None})},
        "currencies": sorted({o.get("currency") for o in rows if o.get("currency")}),
        "status": "unavailable", "reason": None, "headline": None, "detector": None, "evidence": None,
        "score": {"status": "unavailable", "value": None, "band": None, "label": None, "weight_used": 0, "components": [], "reason": None},
        "limitations": [],
    }
    ok = [x for x in listings if x["status"] == "available"]
    if not rows:
        verified_any = db[OBSERVATIONS].count_documents({"product_id": product_id, "history_eligible": True, "observed_at": {"$lte": cutoff}}, limit=1)
        reason = f"{INSUFFICIENT}: no verified observations in this {window_days}-day window." if verified_any else f"{INSUFFICIENT}. {HISTORY_UNAVAILABLE}"
        out["reason"] = reason
    elif len({x["currency"] for x in ok}) > 1:
        out["reason"] = "Listings use different currencies, so their prices aren't compared. Each listing's own result is shown."
    elif not ok:
        ins = [x for x in listings if x["status"] == "insufficient"]
        out["status"] = "insufficient" if ins else "unavailable"
        out["reason"] = (ins[0]["reason"] if ins else f"{INSUFFICIENT}: no listing has a usable current observation. "
                         + " ".join(sorted({x["reason"] for x in listings if x["reason"]})))
    else:
        head = min(ok, key=lambda x: (x["current_minor"], x["listing_id"]))
        det = details[head["listing_id"]]
        cur = det["cur"]
        out["status"] = "available"
        out["headline"] = {k: head[k] for k in ("listing_id", "marketplace", "seller_id", "seller_name")}
        out["detector"] = _detector(det, head, basis)
        d = out["detector"]
        out["score"] = score_components(savings=d["savings_percent"], percentile=d["price_percentile"], advertised=d["advertised_discount_percent"])
        daily = det["daily"]
        first, last = date.fromisoformat(daily[0]["date"]), _aware(cur["observed_at"]).date()
        have = {p["date"] for p in daily} | {last.isoformat()}
        missing = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1) if (first + timedelta(days=i)).isoformat() not in have]
        out["evidence"] = {
            "listing_id": head["listing_id"], "marketplace": head["marketplace"],
            "current_observation": {"observed_at": _iso(cur["observed_at"]), "marketplace": head["marketplace"], "seller_id": head["seller_id"],
                                    "currency": cur.get("currency"), "price_minor": cur.get("price_minor"), "shipping_minor": cur.get("shipping_minor"),
                                    "shipping_known": bool(cur.get("shipping_known")), "value_minor": head["current_minor"],
                                    "reference_price_minor": cur.get("reference_price_minor"),
                                    "advertised_discount_percent": cur.get("advertised_discount_percent"),
                                    "coupon_discount_minor": cur.get("coupon_discount_minor"), "payment_offer": cur.get("payment_offer"),
                                    "availability": cur.get("availability"), "synthetic": cur.get("synthetic"), "source_label": cur.get("source_label")},
            "daily": daily, "baseline_days": len(daily), "first_date": daily[0]["date"], "last_date": daily[-1]["date"], "missing_dates": missing,
            "lowest_minor": min(p["value_minor"] for p in daily), "highest_minor": max(p["value_minor"] for p in daily),
        }
        lim = out["limitations"]
        if missing:
            lim.append(f"{len(missing)} day{'s' if len(missing) != 1 else ''} in this listing's range are missing; they are gaps, not filled in.")
        age = (cutoff - _aware(cur["observed_at"])).days
        if age > STALE_DAYS:
            lim.append(f"The latest observation is {age} days before the cutoff, so the current price may be out of date.")
        if len(daily) < window_days // 2:
            lim.append(f"The baseline uses {len(daily)} observed days out of a {window_days}-day window.")
        if cur.get("coupon_discount_minor") or (cur.get("payment_offer") and cur.get("payment_offer") != "No payment offer"):
            lim.append("Coupons and payment offers are conditional and are not subtracted.")
        if out["score"]["weight_used"] < 100:
            lim.append("No advertised discount was reported, so the score uses 85% of its weight, rescaled.")
    if excluded["timezone_unknown"]:
        out["limitations"].append(f"{excluded['timezone_unknown']} snapshot observation{'s' if excluded['timezone_unknown'] != 1 else ''} without a timezone are not used.")
    if excluded["unknown_shipping"]:
        out["limitations"].append(f"{excluded['unknown_shipping']} observation{'s' if excluded['unknown_shipping'] != 1 else ''} with unknown shipping are left out of the delivered price.")
    if excluded["not_purchasable"]:
        out["limitations"].append(f"{excluded['not_purchasable']} observation{'s' if excluded['not_purchasable'] != 1 else ''} reported out of stock or without availability are left out.")
    if out["source"]["synthetic"]:
        out["limitations"].append("This is synthetic demo data.")
    if out["status"] != "available":
        out["score"]["reason"] = f"Scoring isn't justified: {out['reason']}"
    return out
