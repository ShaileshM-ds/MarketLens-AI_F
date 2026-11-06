"""Buying advice (SCOPE §5): Buy now, Consider waiting or Insufficient evidence, with reasons and
disagreeing signals. Sparse or stale data lowers confidence or abstains.

Built only on the Real Price Detector and Genuine Discount Score (evidence.py) at an explicit UTC cutoff.
No forecast is used: there is no validated forecasting model yet, so advice describes observed history up
to the cutoff and never predicts future prices. Rules are versioned (ADVICE_VERSION).
"""

from datetime import datetime

from pymongo.database import Database

from .evidence import SAVINGS_THRESHOLD, price_evidence
from .history import _aware, _iso

ADVICE_VERSION = "advice-1"
LOW_PERCENTILE = 25.0      # current price higher than at least 75% of observed days
STRONG_SAVINGS = 10.0      # high confidence needs at least this much real saving (or rise)
STRONG_PERCENTILE = 80.0   # ...and a price lower than at least 80% of observed days (buy now)
FRESH_HOURS = 48           # older latest observation lowers confidence
STALE_DAYS = 7             # older latest observation: abstain
MISSING_SHARE = 0.10       # more missing days than this share of the observed range lowers confidence
SHORT_HISTORY_DAYS = 30    # fewer observed days than this lowers confidence
LEVELS = ("low", "medium", "high")
LABELS = {"buy_now": "Buy now", "consider_waiting": "Consider waiting", "insufficient_evidence": "Insufficient evidence"}
NO_FORECAST = ("The recommendation is based on prices observed up to the cutoff, not on predicted future prices. "
               "A forecast, when one is validated, is shown separately and never changes it.")
EXPECTATION_HORIZON = 7


def classify(savings: float, percentile: float) -> str:
    """Buy now only for a real reduction against the usual price. An ordinary (or higher) price is never
    presented as a bargain, whatever the advertised discount says."""
    return "buy_now" if savings >= SAVINGS_THRESHOLD else "consider_waiting"


def _base_level(code: str, savings: float, percentile: float) -> str:
    if code == "buy_now":
        if savings >= STRONG_SAVINGS and percentile >= STRONG_PERCENTILE:
            return "high"
        return "medium" if savings >= SAVINGS_THRESHOLD else "low"
    if savings <= -STRONG_SAVINGS:
        return "high"
    return "medium" if savings <= -SAVINGS_THRESHOLD else "low"


def _down(level: str) -> str:
    return LEVELS[max(0, LEVELS.index(level) - 1)]


def _abstain(out: dict, reason: str) -> dict:
    out["recommendation"] = {"code": "insufficient_evidence", "label": LABELS["insufficient_evidence"], "reason": reason}
    out["confidence"] = {"level": None, "reasons": ["No recommendation is made without enough verified, current evidence."]}
    out["reasons"] = [reason]
    return out


def buying_advice(db: Database, product_id: str, *, cutoff: datetime, window_days: int = 90, basis: str = "base") -> dict | None:
    e = price_evidence(db, product_id, cutoff=cutoff, window_days=window_days, basis=basis)
    if e is None:
        return None
    other_basis = "delivered" if basis == "base" else "base"
    out = {
        "product_id": product_id, "cutoff": e["cutoff"], "window": e["window"], "basis": basis,
        "method": {"version": ADVICE_VERSION, "evidence_version": e["method"]["version"], "savings_threshold": SAVINGS_THRESHOLD,
                   "low_percentile": LOW_PERCENTILE, "strong_savings": STRONG_SAVINGS, "strong_percentile": STRONG_PERCENTILE,
                   "fresh_hours": FRESH_HOURS, "stale_days": STALE_DAYS, "missing_share": MISSING_SHARE,
                   "short_history_days": SHORT_HISTORY_DAYS, "min_days": e["method"]["min_days"]},
        "forecast": {"used": False, "note": NO_FORECAST, "expectation": None, "expectation_note": None},
        "recommendation": None, "confidence": None, "reasons": [], "disagreeing": [], "signals": [],
        "price": None, "score": e["score"], "coverage": None, "freshness": None, "headline": e["headline"],
        "evidence_status": e["status"], "limitations": list(e["limitations"]), "source": e["source"],
    }
    if len(e.get("currencies") or []) > 1:
        return _abstain(out, f"Insufficient evidence: this product's observations use different currencies ({', '.join(e['currencies'])}), which are never compared.")
    if e["status"] != "available":
        return _abstain(out, e["reason"] or "Insufficient historical evidence.")

    d, ev = e["detector"], e["evidence"]
    observed_at = _aware(datetime.fromisoformat(ev["current_observation"]["observed_at"].replace("Z", "+00:00")))
    cut = datetime.fromisoformat(e["cutoff"].replace("Z", "+00:00"))
    age_hours = int((cut - observed_at).total_seconds() // 3600)
    observed_days = ev["baseline_days"] + 1
    range_days = observed_days + len(ev["missing_dates"])
    out["price"] = {"currency": d["currency"], "current_minor": d["current_minor"], "usual_minor": d["baseline_minor"],
                    "savings_percent": d["savings_percent"], "price_percentile": d["price_percentile"], "verdict": d["verdict"],
                    "verdict_label": d["label"], "advertised_discount_percent": d["advertised_discount_percent"],
                    "advertised_support": d["advertised_support"]}
    out["coverage"] = {"observed_days": observed_days, "window_days": window_days, "first_date": ev["first_date"],
                       "last_date": observed_at.date().isoformat(), "missing_days": len(ev["missing_dates"]), "range_days": range_days}
    out["freshness"] = {"observed_at": _iso(observed_at), "age_hours": age_hours, "marketplace": ev["marketplace"]}
    if age_hours > STALE_DAYS * 24:
        return _abstain(out, f"Insufficient evidence: the latest verified observation is {age_hours // 24} days before the cutoff, so it is stale "
                             f"(more than {STALE_DAYS} days).")

    s, p = d["savings_percent"], d["price_percentile"]
    code = classify(s, p)
    level = _base_level(code, s, p)
    price_word = "delivered price" if basis == "delivered" else "price"
    reasons = []
    if s >= SAVINGS_THRESHOLD:
        reasons.append(f"The current {price_word} is {s}% below its usual (median) level over the {window_days}-day window.")
    elif s <= -SAVINGS_THRESHOLD:
        reasons.append(f"The current {price_word} is {abs(s)}% above its usual (median) level over the {window_days}-day window.")
    else:
        reasons.append(f"No genuine discount: the current {price_word} is within {SAVINGS_THRESHOLD:g}% of its usual level ({s:+}%), "
                       "so it is an ordinary price, not a bargain. Observed history shows no saving from buying now.")
    if p < LOW_PERCENTILE:
        reasons.append(f"It was cheaper on more than {100 - LOW_PERCENTILE:g}% of observed days in the window (lower than only {p}% of them).")
    else:
        reasons.append(f"It is lower than {p}% of observed days in the window.")
    if code == "consider_waiting" and d["reference"]["increased"]:
        reasons.append(f"The seller's reference price was raised: {d['reference']['note']}")
    if code == "consider_waiting" and d["advertised_support"] == "not_supported":
        reasons.append(f"The advertised discount isn't supported: {d['advertised_note']}")
    if e["score"]["value"] is not None:
        reasons.append(f"Genuine Discount Score {e['score']['value']} / 100: {e['score']['label'].lower()}.")

    signals = [
        {"key": "real_savings", "label": "Real savings vs usual price", "value": f"{s}%", "supports": "buy" if s >= SAVINGS_THRESHOLD else "wait" if s <= -SAVINGS_THRESHOLD else "neutral"},
        {"key": "price_percentile", "label": "Lower than observed days", "value": f"{p}%", "supports": "wait" if p < LOW_PERCENTILE else "buy" if p >= STRONG_PERCENTILE else "neutral"},
        {"key": "score", "label": "Genuine Discount Score", "value": f"{e['score']['value']} / 100",
         "supports": {"strong": "buy", "moderate": "neutral", "weak": "neutral"}[e["score"]["band"]]},
    ]
    disagreeing = []
    if code == "buy_now":
        if d["reference"]["increased"]:
            disagreeing.append({"key": "reference_increase", "label": "Seller reference price raised", "detail": d["reference"]["note"]})
        if d["advertised_support"] == "not_supported":
            disagreeing.append({"key": "advertised_not_supported", "label": "Advertised discount not supported", "detail": d["advertised_note"]})
    elif e["score"]["band"] == "strong":
        disagreeing.append({"key": "strong_score", "label": "Strong Genuine Discount Score", "detail": e["score"]["label"]})

    other = price_evidence(db, product_id, cutoff=cut, window_days=window_days, basis=other_basis)
    other_word = "Confirmed delivered price" if other_basis == "delivered" else "Base price"
    if other and other["status"] == "available":
        od = other["detector"]
        signals.append({"key": "other_basis", "label": f"{other_word} vs usual", "value": f"{od['savings_percent']}%",
                        "supports": "buy" if od["savings_percent"] >= SAVINGS_THRESHOLD else "wait" if od["savings_percent"] <= -SAVINGS_THRESHOLD else "neutral"})
        if classify(od["savings_percent"], od["price_percentile"]) != code or (od["verdict"] != d["verdict"]):
            disagreeing.append({"key": f"{other_basis}_basis", "label": f"{other_word} tells a different story",
                                "detail": f"On the {other_word.lower()} the change vs usual is {od['savings_percent']:+}% ({od['label'].lower()})."})
    else:
        out["limitations"].append(f"{other_word} couldn't be cross-checked: {(other or {}).get('reason') or 'not available'}")

    conf = []
    if age_hours > FRESH_HOURS:
        level = _down(level)
        conf.append(f"The latest observation is {age_hours // 24} days old at the cutoff.")
    if range_days and len(ev["missing_dates"]) / range_days > MISSING_SHARE:
        level = _down(level)
        conf.append(f"{len(ev['missing_dates'])} of {range_days} days are missing in the observed range.")
    if observed_days < SHORT_HISTORY_DAYS:
        level = _down(level)
        conf.append(f"Only {observed_days} observed days (fewer than {SHORT_HISTORY_DAYS}).")
    if disagreeing:
        level = _down(level)
        conf.append(f"{len(disagreeing)} disagreeing signal{'s' if len(disagreeing) != 1 else ''}.")
    if not conf:
        conf.append("Fresh, well-covered observations and no disagreeing signals." if level == "high" else
                    "The signal itself is moderate or weak; data coverage and freshness don't lower it further.")

    lead = reasons[1] if (code == "consider_waiting" and s > -SAVINGS_THRESHOLD and p < LOW_PERCENTILE) else reasons[0]  # the deciding signal
    out["recommendation"] = {"code": code, "label": LABELS[code], "reason": lead}
    out["forecast"]["expectation"], out["forecast"]["expectation_note"] = _expectation(db, product_id, cut, basis)
    out["confidence"] = {"level": level, "reasons": conf}
    out["reasons"], out["signals"], out["disagreeing"] = reasons, signals, disagreeing
    return out


def _expectation(db: Database, product_id: str, cutoff: datetime, basis: str):
    """A forecast-based expectation, shown separately: only when the model beat the baseline in backtests."""
    from .forecast import product_forecast

    f = product_forecast(db, product_id, cutoff=cutoff, basis=basis)
    h = next((x for x in (f or {}).get("horizons", []) if x["days"] == EXPECTATION_HORIZON), None)
    if not f or f["status"] != "available" or not h or h["status"] != "available":
        return None, "No validated forecast is available for this product."
    if h["chosen"] == "naive":
        return None, (f"The {EXPECTATION_HORIZON}-day forecast model didn't beat the last-price baseline in backtests, "
                      "so no forecast-based expectation is given.")
    m = {x["key"]: x for x in h["models"]}
    fc = h["forecast"]
    return {
        "horizon_days": EXPECTATION_HORIZON, "date": fc["date"], "currency": f["currency"], "value_minor": fc["value_minor"],
        "low_minor": fc["low_minor"], "high_minor": fc["high_minor"], "interval": fc["interval"], "model": h["chosen"],
        "model_label": h["chosen_label"], "mae_minor": m[h["chosen"]]["mae_minor"], "baseline_mae_minor": m["naive"]["mae_minor"],
        "backtest_points": m[h["chosen"]]["n"],
        "note": "An estimate from past prices with its measured backtest error. It is not a guarantee and does not change the recommendation.",
    }, None
