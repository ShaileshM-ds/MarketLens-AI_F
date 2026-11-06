"""Dark-pattern audit rules (SCOPE §5). Each finding has a rule version, severity, confidence, supporting
observations and benign explanations. A rule whose required data is missing is disabled, never guessed.

Kinds: "observed" (a recorded fact, e.g. stock and availability disagree in one observation), "calculated"
(from the Real Price Detector over verified history), "heuristic" (a pattern that may be benign).
Findings are flags for review, not legal findings or accusations.
Cutoff: verified observations are read up to the cutoff; timezone-unknown snapshot observations only if they
were ingested by the cutoff (they have no observation time of their own).
"""

from datetime import datetime, time, timedelta

from pymongo.database import Database

from .db import OBSERVATIONS, PRODUCTS
from .evidence import price_evidence
from .explorer import availability_class
from .history import UTC, WINDOWS, HistoryError, _aware, _iso, require_utc

AUDIT_VERSION = "audit-1"
URGENCY_MIN_DAYS = 14
LOW_STOCK = 5
NOTE = ("These are evidence-based flags for review, not a legal finding or an accusation against any seller. "
        "Each one lists ordinary explanations and the data it relies on.")
RULES = {
    "unsupported_discount": {"title": "Advertised discount not supported by price history", "version": "1.0", "kind": "calculated",
                             "required": "verified price history (14+ days) and an advertised discount"},
    "reference_inflation": {"title": "Reference price raised", "version": "1.0", "kind": "calculated",
                            "required": "verified history of the seller's reference price"},
    "repeated_urgency": {"title": "Repeated urgency message while stock stayed normal", "version": "1.0", "kind": "heuristic",
                         "required": "urgency messages and stock quantities on verified observations"},
    "stock_contradiction": {"title": "Availability and stock quantity disagree", "version": "1.0", "kind": "observed",
                            "required": "availability and stock quantity on the same observation"},
    "discount_arithmetic": {"title": "Displayed discount doesn't match displayed prices", "version": "1.0", "kind": "observed",
                            "required": "price, reference price and advertised discount on the same observation"},
}


def _obs(o: dict) -> dict:
    return {"listing_id": o.get("listing_id"), "marketplace": o.get("marketplace"), "seller_id": o.get("seller_id"),
            "observed_at": _iso(o.get("observed_at")), "source_timestamp": o.get("source_timestamp"),
            "timestamp_quality": o.get("timestamp_quality"), "currency": o.get("currency"), "price_minor": o.get("price_minor"),
            "reference_price_minor": o.get("reference_price_minor"), "advertised_discount_percent": o.get("advertised_discount_percent"),
            "availability": o.get("availability"), "stock_quantity": o.get("stock_quantity"), "urgency_message": o.get("urgency_message"),
            "flags": o.get("flags") or [], "synthetic": o.get("synthetic"), "source_label": o.get("source_label")}


def _sample(items: list, n: int = 10) -> list:
    if len(items) <= n:
        return items
    step = (len(items) - 1) / (n - 1)
    return [items[round(i * step)] for i in range(n)]


def _finding(rule_id: str, *, severity: str, confidence: str, confidence_reason: str, explanation: str, support: list, benign: list, limitations: list) -> dict:
    r = RULES[rule_id]
    return {"rule_id": rule_id, "rule_version": f"{AUDIT_VERSION}/{r['version']}", "title": r["title"], "kind": r["kind"], "severity": severity,
            "confidence": {"level": confidence, "reason": confidence_reason}, "explanation": explanation,
            "supporting_observations": support, "benign_explanations": benign, "limitations": limitations}


def product_audit(db: Database, product_id: str, *, cutoff: datetime, window_days: int = 90) -> dict | None:
    cutoff = require_utc(cutoff, "cutoff")
    if window_days not in WINDOWS:
        raise HistoryError(f"window must be one of {', '.join(map(str, WINDOWS))} days.")
    if not db[PRODUCTS].find_one({"_id": product_id}, {"_id": 1}):
        return None
    start = datetime.combine(cutoff.date() - timedelta(days=window_days - 1), time.min, UTC)
    proj = {"raw": 0, "content_hash": 0}
    verified = list(db[OBSERVATIONS].find({"product_id": product_id, "history_eligible": True, "observed_at": {"$gte": start, "$lte": cutoff}}, proj)
                    .sort([("observed_at", 1), ("_id", 1)]))
    snapshots = list(db[OBSERVATIONS].find({"product_id": product_id, "history_eligible": {"$ne": True}, "provenance.ingested_at": {"$lte": cutoff}}, proj)
                     .sort("_id", 1))
    seen = verified + snapshots
    e = price_evidence(db, product_id, cutoff=cutoff, window_days=window_days, basis="base")
    findings, rules = [], []

    def rule(rule_id: str, status: str, reason: str):
        r = RULES[rule_id]
        rules.append({"rule_id": rule_id, "title": r["title"], "version": f"{AUDIT_VERSION}/{r['version']}", "kind": r["kind"],
                      "required": r["required"], "status": status, "reason": reason})

    # --- calculated rules from the Real Price Detector ---
    if e["status"] != "available":
        why = f"Disabled: needs verified price history. {e['reason']}"
        rule("unsupported_discount", "disabled", why)
        rule("reference_inflation", "disabled", why)
    else:
        d, ev = e["detector"], e["evidence"]
        days = ev["baseline_days"]
        conf = "high" if days >= 60 else "medium" if days >= 30 else "low"
        conf_reason = f"Baseline of {days} observed days on {ev['marketplace']}."
        cur = next((o for o in verified if _iso(o["observed_at"]) == ev["current_observation"]["observed_at"] and o["listing_id"] == ev["listing_id"]), None)
        cur_view = [_obs(cur)] if cur else []
        lim = [f"Based on the {window_days}-day window up to the cutoff, on the store listing with the lowest current price."]
        if d["advertised_discount_percent"] is None:
            rule("unsupported_discount", "disabled", "Disabled: no advertised discount was reported.")
        elif d["advertised_support"] == "not_supported":
            findings.append(_finding("unsupported_discount", severity="medium", confidence=conf, confidence_reason=conf_reason,
                explanation=f"The listing advertises {d['advertised_discount_percent']:g}% off, but its price is {d['savings_percent']:+}% versus its usual "
                            f"(median) price over {days} observed days. {d['advertised_note']}",
                support=cur_view, limitations=lim, benign=[
                    "The reference price may be the manufacturer's list price (MRP), which many stores discount from permanently.",
                    "The discount may be real against a period before this window."]))
            rule("unsupported_discount", "triggered", "The advertised discount exceeds the observed reduction.")
        else:
            rule("unsupported_discount", "not_triggered", "The advertised discount is consistent with observed prices or partly supported.")
        ref = d["reference"]
        if ref["increased"] is None:
            rule("reference_inflation", "disabled", "Disabled: the seller's reference price isn't known for enough days.")
        elif ref["increased"]:
            sev = "high" if ref["change_percent"] >= 50 and abs(d["savings_percent"]) < 5 else "medium"
            first = next((p for p in ev["daily"] if p["date"] == ref["since"]), None)
            support = cur_view + ([{"date": first["date"], "value_minor": first["value_minor"], "reference_price_minor": first["reference_minor"],
                                    "note": "First day at the raised reference level"}] if first else [])
            findings.append(_finding("reference_inflation", severity=sev, confidence=conf, confidence_reason=conf_reason,
                explanation=f"{ref['note']} The observed price changed {d['savings_percent']:+}% versus usual.",
                support=support, limitations=lim, benign=[
                    "The manufacturer may have raised its list price (MRP).",
                    "A new model or packaging may carry a new reference price."]))
            rule("reference_inflation", "triggered", f"Reference price {ref['change_percent']}% above its window median.")
        else:
            rule("reference_inflation", "not_triggered", "The reference price is close to its usual level.")

    # --- heuristic: repeated urgency while stock stayed normal (verified observations only) ---
    if not verified:
        rule("repeated_urgency", "disabled", "Disabled: needs verified observations with times.")
    elif not any("urgency_message" in o for o in verified):
        rule("repeated_urgency", "disabled", "Disabled: this data has no urgency-message field.")
    else:
        normal, low, unknown = {}, set(), set()
        for o in verified:
            if not o.get("urgency_message"):
                continue
            dkey = _aware(o["observed_at"]).date()
            q, cls = o.get("stock_quantity"), availability_class(o.get("availability"))
            if q is None or cls == "unknown":
                unknown.add(dkey)
            elif cls == "limited_stock" or q <= LOW_STOCK:
                low.add(dkey)
            elif cls == "in_stock":
                normal.setdefault(dkey, o)
        normal_days = sorted(set(normal) - low)
        if len(normal_days) >= URGENCY_MIN_DAYS:
            msgs = sorted({normal[k]["urgency_message"] for k in normal_days})
            min_stock = min(normal[k]["stock_quantity"] for k in normal_days)
            findings.append(_finding("repeated_urgency", severity="low", confidence="medium" if len(normal_days) >= 30 else "low",
                confidence_reason=f"{len(normal_days)} days with the message and normal reported stock.",
                explanation=f"The message “{msgs[0]}”{f' (and {len(msgs) - 1} other)' if len(msgs) > 1 else ''} appeared on {len(normal_days)} days "
                            f"while reported stock stayed at {min_stock} or more and availability was In Stock. An urgency message is not deceptive by itself.",
                support=[_obs(normal[k]) for k in _sample(normal_days)],
                limitations=[f"{len(low)} days had low stock (consistent with the message); {len(unknown)} days had unknown stock and weren't judged."],
                benign=["The message may be a general store banner, not a statement about this listing's stock.",
                        "Reported stock may be for a warehouse, not what one buyer can order."]))
            rule("repeated_urgency", "triggered", f"Urgency on {len(normal_days)} days with normal stock (at least {URGENCY_MIN_DAYS} needed).")
        else:
            rule("repeated_urgency", "not_triggered",
                 f"Urgency with normal stock on {len(normal_days)} days (at least {URGENCY_MIN_DAYS} needed); {len(low)} days were consistent with low stock.")

    # --- observed facts on single observations (snapshots included) ---
    for rule_id, flag, sev, text, benign in (
        ("stock_contradiction", "stock_availability_contradiction", "low",
         "{n} observation{s} report an availability that disagrees with the stock quantity (for example Out of Stock with stock above zero). Values are shown as recorded, never corrected.",
         ["Availability and stock may be updated by different systems at different times.", "Stock may be reserved for existing orders."]),
        ("discount_arithmetic", "discount_mismatch", "low",
         "{n} observation{s} show an advertised discount that differs from the reduction calculated from the displayed price and reference price by more than 0.5 points.",
         ["Rounding or a discount calculated on a different reference (for example before tax).", "Prices and the discount label may update at different times."]),
    ):
        has_fields = any(o.get("availability") is not None and o.get("stock_quantity") is not None for o in seen) if rule_id == "stock_contradiction" else \
            any(o.get("reference_price_minor") is not None and o.get("advertised_discount_percent") is not None for o in seen)
        if not has_fields:
            rule(rule_id, "disabled", f"Disabled: needs {RULES[rule_id]['required']}.")
            continue
        hits = [o for o in seen if flag in (o.get("flags") or [])]
        if hits:
            findings.append(_finding(rule_id, severity=sev, confidence="high", confidence_reason="Recorded directly in the stored observations.",
                explanation=text.format(n=len(hits), s="s" if len(hits) != 1 else ""), support=[_obs(o) for o in _sample(hits)],
                limitations=["Snapshot observations without a timezone are included only if ingested by the cutoff."] if snapshots else [],
                benign=benign))
            rule(rule_id, "triggered", f"{len(hits)} observation{'s' if len(hits) != 1 else ''}.")
        else:
            rule(rule_id, "not_triggered", "No observation shows this.")

    sev_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (sev_order[f["severity"]], f["rule_id"]))
    synth = [bool(o.get("synthetic")) for o in seen]
    return {"product_id": product_id, "cutoff": _iso(cutoff), "window": {"days": window_days, "start": _iso(start), "end": _iso(cutoff)},
            "version": AUDIT_VERSION, "note": NOTE, "findings": findings, "rules": rules,
            "observations_read": {"verified": len(verified), "snapshot": len(snapshots)},
            "source": {"synthetic": all(synth) if synth else None, "source_labels": sorted({o.get("source_label") for o in seen if o.get("source_label")})}}
