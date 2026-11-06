"""Price forecasting and Future Price Memory (SCOPE §5). Version FORECAST_VERSION.

Forecasting, per store listing (same seller, store and currency as the evidence headline):
- Daily series = lowest usable verified observation each day (same rules as evidence.py) up to an explicit
  UTC cutoff. Missing days stay missing; they are never filled.
- Models: the baseline `naive` (last observed daily price) and `recent_median` (median of the last 14
  observed daily prices: robust to one-off sales). Both are deterministic, with no fitted parameters.
- Rolling-origin backtest per horizon (7/14/30 days): each origin uses only days up to that origin, and the
  target is the observed price exactly h days later (skipped when that day is missing). Origins are taken in
  date order; nothing is shuffled. The last MAX_ORIGINS origins are used.
- Selection is per forecast series: one store listing (so one product, seller, store and currency), judged only
  on its own rolling-origin backtest up to the cutoff. The candidate is chosen only if its MAE is at least
  MIN_IMPROVEMENT % lower than the baseline's for that series; otherwise the baseline is used (SCOPE: fall back
  to a baseline if the model does not improve). Other series never influence the choice.
- 80% interval (forecast-2): split-conformal on relative absolute backtest errors |actual / predicted - 1|.
  The half-width is the ceil((n + 1) x 0.8)-th smallest of the n errors; with too few errors there is no interval.
  Coverage and width are measured walk-forward: each origin's interval uses only errors whose targets were
  observed by that origin, so no later evaluation error ever shapes an earlier interval.
  forecast-1 used signed-error nearest-rank quantiles; its coverage and width are still reported for comparison.
Future Price Memory: completed 1/3/7/14-day outcomes after past price drops, non-overlapping episodes,
counts and frequencies (never presented as probabilities).
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pymongo.database import Database

from .db import OBSERVATIONS
from .evidence import _median, _unusable, price_evidence
from .history import UTC, BASES, HistoryError, _aware, _iso, _value, require_utc

FORECAST_VERSION = "forecast-2"
INTERVAL_METHOD = "conformal-relative-abs"
PREVIOUS_INTERVAL_METHOD = "signed-error nearest-rank quantiles (forecast-1)"
HORIZONS = (7, 14, 30)
MODELS = {"naive": "Last observed price (baseline)", "recent_median": "Median of the last 14 observed days"}
MEDIAN_DAYS = 14
MIN_TRAIN_DAYS = 14
MIN_ORIGINS = 20
MAX_ORIGINS = 120
MIN_IMPROVEMENT = 5.0      # % lower MAE than the baseline needed to use the model
INTERVAL_LEVEL = 80
MIN_RESIDUALS = 10
LOOKBACK_DAYS = 365
STALE_DAYS = 7
DROP = 0.10                # Future Price Memory: a drop of 10%+ below the previous 14 observed days' median
RETURN_WITHIN = 0.05       # "returned": back within 5% of the pre-drop median
FURTHER = 0.05             # "fell further": 5%+ below the drop-day price
MEMORY_DAYS = (1, 3, 7, 14)
_Q = Decimal(1)


def _round(x) -> int:
    return int(Decimal(x).quantize(_Q, rounding=ROUND_HALF_UP))


def _q2(x) -> float:
    return float(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def predict(model: str, values: list[int]) -> int:
    if model == "naive":
        return values[-1]
    if model == "recent_median":
        return _round(_median(values[-MEDIAN_DAYS:]))
    raise ValueError(model)


def backtest(series: list[tuple[date, int]], h: int, model: str) -> list[dict]:
    """Rolling-origin backtest in date order. Each prediction uses only days up to its origin."""
    by_date = dict(series)
    out = []
    for i in range(MIN_TRAIN_DAYS - 1, len(series)):
        origin = series[i][0]
        target = origin + timedelta(days=h)
        if target not in by_date:
            continue
        pred = predict(model, [v for _, v in series[: i + 1]])
        out.append({"origin": origin, "target": target, "pred": pred, "actual": by_date[target]})
    return out[-MAX_ORIGINS:]


def _quantile(xs: list[int], q: float) -> int:
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(Decimal(q * len(s)).to_integral_value(rounding=ROUND_HALF_UP)) - 1))
    return s[k]


def conformal_quantile(xs: list, level: float):
    """Finite-sample split-conformal quantile: the ceil((n + 1) x level)-th smallest value, or None if n is too small."""
    n = len(xs)
    k = int((Decimal(n + 1) * Decimal(str(level))).to_integral_value(rounding="ROUND_CEILING"))
    if n == 0 or k > n:
        return None
    return sorted(xs)[k - 1]


def _rel(b: dict) -> Decimal:
    return abs(Decimal(b["actual"]) / Decimal(b["pred"]) - 1) if b["pred"] else Decimal(0)


def walk_forward_intervals(bt: list[dict], level: float = INTERVAL_LEVEL / 100) -> dict:
    """Calibrated intervals at each backtest origin from errors known by that origin (target <= origin)."""
    points = []
    for b in bt:
        known = [x for x in bt if x["target"] <= b["origin"]]
        if len(known) < MIN_RESIDUALS:
            continue
        q = conformal_quantile([_rel(x) for x in known], level)
        if q is None:
            continue
        low, high = Decimal(b["pred"]) * (1 - q), Decimal(b["pred"]) * (1 + q)
        points.append({"origin": b["origin"], "known_targets": [x["target"] for x in known], "low": _round(max(Decimal(0), low)),
                       "high": _round(high), "hit": low <= b["actual"] <= high, "width_percent": float(2 * q * 100)})
    return _summary(points)


def walk_forward_previous(bt: list[dict]) -> dict:
    """forecast-1 intervals (signed-error nearest-rank quantiles), measured the same way, for comparison."""
    lo_q, hi_q = (100 - INTERVAL_LEVEL) / 200, 1 - (100 - INTERVAL_LEVEL) / 200
    points = []
    for b in bt:
        known = [x["actual"] - x["pred"] for x in bt if x["target"] <= b["origin"]]
        if len(known) < MIN_RESIDUALS:
            continue
        low, high = b["pred"] + _quantile(known, lo_q), b["pred"] + _quantile(known, hi_q)
        points.append({"origin": b["origin"], "low": low, "high": high, "hit": low <= b["actual"] <= high,
                       "width_percent": float(Decimal(high - low) / Decimal(b["pred"]) * 100) if b["pred"] else 0.0})
    return _summary(points)


def _summary(points: list[dict]) -> dict:
    n = len(points)
    return {"points": points, "n": n,
            "coverage_percent": _q2(Decimal(sum(p["hit"] for p in points)) / n * 100) if n else None,
            "mean_width_percent": _q2(Decimal(str(sum(p["width_percent"] for p in points))) / n) if n else None}


def _metrics(bt: list[dict]) -> dict:
    n = len(bt)
    mae = sum(abs(b["pred"] - b["actual"]) for b in bt) / n if n else None
    mape = sum(abs(b["pred"] - b["actual"]) / b["actual"] for b in bt if b["actual"]) / n * 100 if n else None
    return {"n": n, "mae_minor": _round(mae) if mae is not None else None, "mape_percent": _q2(mape) if mape is not None else None}


def evaluate(series: list[tuple[date, int]], h: int) -> dict:
    out = {"days": h, "status": "insufficient", "reason": None, "chosen": None, "chosen_label": None, "models": [],
           "improvement_percent": None, "note": None, "forecast": None, "backtest_first": None, "backtest_last": None}
    bts = {m: backtest(series, h, m) for m in MODELS}
    n = len(bts["naive"])
    if n < MIN_ORIGINS:
        out["reason"] = f"Too few completed backtest points for {h} days ({n}; at least {MIN_ORIGINS} needed), so no {h}-day forecast is shown."
        return out
    metrics = {m: _metrics(b) for m, b in bts.items()}
    out["models"] = [{"key": m, "label": MODELS[m], **metrics[m]} for m in MODELS]
    base, cand = metrics["naive"]["mae_minor"], metrics["recent_median"]["mae_minor"]
    improvement = _q2((Decimal(base) - Decimal(cand)) / Decimal(base) * 100) if base else 0.0
    out["improvement_percent"] = improvement
    chosen = "recent_median" if improvement >= MIN_IMPROVEMENT else "naive"
    out.update(status="available", chosen=chosen, chosen_label=MODELS[chosen],
               backtest_first=bts[chosen][0]["origin"].isoformat(), backtest_last=bts[chosen][-1]["origin"].isoformat())
    if chosen == "recent_median":
        out["note"] = (f"The 14-day median beat the last-price baseline by {improvement}% (mean absolute error) in this listing's own "
                       "backtest, so it is used.")
    else:
        out["note"] = f"The 14-day median did not beat the last-price baseline by at least {MIN_IMPROVEMENT:g}% ({improvement:+}%), so the baseline is used."

    wf = walk_forward_intervals(bts[chosen])
    prev = walk_forward_previous(bts[chosen])
    last_day = series[-1][0]
    value = predict(chosen, [v for _, v in series])
    rel = [_rel(b) for b in bts[chosen]]  # every backtest target is observed by the last day: all errors are known
    q = conformal_quantile(rel, INTERVAL_LEVEL / 100) if len(rel) >= MIN_RESIDUALS else None
    interval = {"level_percent": INTERVAL_LEVEL, "method": INTERVAL_METHOD, "measured_coverage_percent": wf["coverage_percent"],
                "measured_on": wf["n"], "mean_width_percent": wf["mean_width_percent"],
                "half_width_percent": _q2(q * 100) if q is not None else None,
                "previous_method": {"name": PREVIOUS_INTERVAL_METHOD, "measured_coverage_percent": prev["coverage_percent"],
                                    "mean_width_percent": prev["mean_width_percent"], "measured_on": prev["n"]}}
    out["forecast"] = {
        "date": (last_day + timedelta(days=h)).isoformat(), "from_date": last_day.isoformat(), "value_minor": value,
        "low_minor": _round(max(Decimal(0), Decimal(value) * (1 - q))) if q is not None else None,
        "high_minor": _round(Decimal(value) * (1 + q)) if q is not None else None, "interval": interval,
    }
    return out


def price_memory(series: list[tuple[date, int]]) -> dict:
    """Completed outcomes after past drops; episodes never overlap. Counts, not probabilities."""
    by_date = dict(series)
    last = series[-1][0] if series else None
    events, block_until = [], None
    for i in range(MIN_TRAIN_DAYS, len(series)):
        d, v = series[i]
        if block_until and d <= block_until:
            continue
        pre = _median([x for _, x in series[i - MIN_TRAIN_DAYS:i]])
        if Decimal(v) > pre * Decimal(str(1 - DROP)):
            continue
        outcomes = {}
        for k in MEMORY_DAYS:
            t = d + timedelta(days=k)
            if t > last:
                outcomes[str(k)] = {"date": t.isoformat(), "outcome": "not_completed", "value_minor": None}
            elif t not in by_date:
                outcomes[str(k)] = {"date": t.isoformat(), "outcome": "no_observation", "value_minor": None}
            else:
                x = by_date[t]
                o = ("returned" if Decimal(x) >= pre * Decimal(str(1 - RETURN_WITHIN)) else
                     "fell_further" if Decimal(x) <= Decimal(v) * Decimal(str(1 - FURTHER)) else "stayed_low")
                outcomes[str(k)] = {"date": t.isoformat(), "outcome": o, "value_minor": x}
        events.append({"date": d.isoformat(), "value_minor": v, "before_median_minor": _round(pre),
                       "drop_percent": _q2((pre - Decimal(v)) / pre * 100), "outcomes": outcomes})
        block_until = d + timedelta(days=max(MEMORY_DAYS))
    summary = {}
    for k in MEMORY_DAYS:
        done = [e["outcomes"][str(k)]["outcome"] for e in events if e["outcomes"][str(k)]["outcome"] in ("returned", "stayed_low", "fell_further")]
        summary[str(k)] = {"completed": len(done), "returned": done.count("returned"), "stayed_low": done.count("stayed_low"),
                           "fell_further": done.count("fell_further"),
                           "pending": sum(e["outcomes"][str(k)]["outcome"] == "not_completed" for e in events)}
    current = None
    if events and series:
        e = events[-1]
        d0 = date.fromisoformat(e["date"])
        if last <= d0 + timedelta(days=max(MEMORY_DAYS)) and Decimal(series[-1][1]) <= Decimal(e["before_median_minor"]) * Decimal(str(1 - DROP)):
            current = e
    return {"events": events, "summary": summary, "current_event": current,
            "definition": f"A similar event is a daily price at least {DROP * 100:g}% below the median of the previous {MIN_TRAIN_DAYS} observed days. "
                          f"Episodes don't overlap: a new one can start only {max(MEMORY_DAYS)} days after the last.",
            "note": "Counts of what happened after past drops of this product. Only completed outcomes are counted. "
                    "These are past frequencies, not a probability or a prediction."}


def listing_series(db: Database, listing_id: str, *, cutoff: datetime, basis: str) -> tuple[list[tuple[date, int]], dict]:
    start = datetime.combine(cutoff.date() - timedelta(days=LOOKBACK_DAYS - 1), time.min, UTC)
    rows = db[OBSERVATIONS].find({"listing_id": listing_id, "history_eligible": True, "observed_at": {"$gte": start, "$lte": cutoff}},
                                 {"raw": 0, "content_hash": 0}).sort([("observed_at", 1), ("_id", 1)])
    days: dict[date, list[int]] = defaultdict(list)
    excluded: dict[str, int] = defaultdict(int)
    for o in rows:
        why = _unusable(o, basis)
        if why:
            excluded[why] += 1
            continue
        days[_aware(o["observed_at"]).date()].append(_value(o, basis))
    return [(d, min(v)) for d, v in sorted(days.items())], dict(excluded)


def product_forecast(db: Database, product_id: str, *, cutoff: datetime, basis: str = "base") -> dict | None:
    cutoff = require_utc(cutoff, "cutoff")
    if basis not in BASES:
        raise HistoryError("basis must be 'base' or 'delivered'.")
    e = price_evidence(db, product_id, cutoff=cutoff, window_days=90, basis=basis)
    if e is None:
        return None
    out = {"product_id": product_id, "cutoff": e["cutoff"], "basis": basis, "status": "unavailable", "reason": None,
           "predicted_values_are_observations": False,
           "method": {"version": FORECAST_VERSION, "models": MODELS, "horizons": list(HORIZONS), "min_origins": MIN_ORIGINS,
                      "max_origins": MAX_ORIGINS, "min_improvement_percent": MIN_IMPROVEMENT, "interval_level_percent": INTERVAL_LEVEL,
                      "lookback_days": LOOKBACK_DAYS, "stale_days": STALE_DAYS},
           "headline": e["headline"], "currency": None, "history": [], "horizons": [], "memory": None,
           "coverage": None, "freshness": None, "limitations": [], "source": e["source"]}
    if len(e.get("currencies") or []) > 1:
        out["reason"] = f"Observations use different currencies ({', '.join(e['currencies'])}); no forecast mixes them."
        return out
    if e["status"] != "available":
        out["reason"] = f"No forecast: {e['reason']}"
        return out
    lid = e["headline"]["listing_id"]
    series, excluded = listing_series(db, lid, cutoff=cutoff, basis=basis)
    last = series[-1][0]
    age_days = (cutoff.date() - last).days
    out["currency"] = e["detector"]["currency"]
    out["freshness"] = {"last_observed_date": last.isoformat(), "age_days": age_days, "marketplace": e["headline"]["marketplace"]}
    out["coverage"] = {"observed_days": len(series), "first_date": series[0][0].isoformat(), "last_date": last.isoformat(),
                       "missing_days": (last - series[0][0]).days + 1 - len(series), "excluded": excluded}
    if age_days > STALE_DAYS:
        out["reason"] = f"No forecast: the latest usable observation is {age_days} days before the cutoff, so the data is stale."
        return out
    out["history"] = [{"date": d.isoformat(), "value_minor": v} for d, v in series[-120:]]
    out["horizons"] = [evaluate(series, h) for h in HORIZONS]
    out["memory"] = price_memory(series)
    ok = [h for h in out["horizons"] if h["status"] == "available"]
    out["status"] = "available" if ok else "insufficient"
    out["reason"] = None if ok else "Not enough verified history to backtest any horizon."
    lim = out["limitations"]
    lim.append("Forecasts are estimates from past prices of this store listing, not observed prices and not a guarantee.")
    lim.append("The models use only this listing's own price history; promotions, stock and market events aren't modelled.")
    if out["coverage"]["missing_days"]:
        lim.append(f"{out['coverage']['missing_days']} missing days in the history; backtest points that needed them were skipped.")
    if any(h["chosen"] == "naive" for h in ok):
        lim.append("Where the model didn't beat the baseline, the forecast is simply the last observed price.")
    if e["source"]["synthetic"]:
        lim.append("This is synthetic demo data.")
    return out


def evaluation_report(db: Database, *, cutoff: datetime, basis: str = "base", max_products: int = 500) -> dict:
    """Rolling-origin evaluation across a workspace: one store listing per product (the evidence headline),
    only data up to the cutoff, each horizon separately. Each series keeps its own model choice; pooled errors,
    coverage and width are reported, never used to choose models."""
    from .evidence import price_evidence

    cutoff = require_utc(cutoff, "cutoff")
    pids = sorted(db[OBSERVATIONS].distinct("product_id", {"history_eligible": True, "observed_at": {"$lte": cutoff}}))[:max_products]
    listings, insufficient, synthetic, per = [], [], [], []
    for pid in pids:
        e = price_evidence(db, pid, cutoff=cutoff, window_days=90, basis=basis)
        if len(e.get("currencies") or []) > 1:
            insufficient.append({"product_id": pid, "reason": f"Different currencies ({', '.join(e['currencies'])}); never mixed."})
            continue
        if e["status"] != "available":
            insufficient.append({"product_id": pid, "reason": e["reason"]})
            continue
        lid = e["headline"]["listing_id"]
        series, _ = listing_series(db, lid, cutoff=cutoff, basis=basis)
        if (cutoff.date() - series[-1][0]).days > STALE_DAYS:
            insufficient.append({"product_id": pid, "reason": "Stale: no usable observation in the last 7 days before the cutoff."})
            continue
        evs = {h: evaluate(series, h) for h in HORIZONS}
        if not any(ev["status"] == "available" for ev in evs.values()):
            insufficient.append({"product_id": pid, "reason": "Too few backtest points for every horizon."})
            continue
        synthetic.append(bool(e["source"]["synthetic"]))
        listings.append({"product_id": pid, "listing_id": lid, "marketplace": e["headline"]["marketplace"], "seller_id": e["headline"]["seller_id"]})
        per.append((series, evs))
    horizons = []
    for h in HORIZONS:
        n = 0
        abs_b = abs_c = ape_b = ape_c = Decimal(0)
        origins, rows = [], []
        for series, evs in per:
            if evs[h]["status"] != "available":
                continue
            bn, bc = backtest(series, h, "naive"), backtest(series, h, "recent_median")
            n += len(bn)
            abs_b += sum(Decimal(abs(b["pred"] - b["actual"])) for b in bn)
            abs_c += sum(Decimal(abs(b["pred"] - b["actual"])) for b in bc)
            ape_b += sum(Decimal(abs(b["pred"] - b["actual"])) / Decimal(b["actual"]) for b in bn if b["actual"])
            ape_c += sum(Decimal(abs(b["pred"] - b["actual"])) / Decimal(b["actual"]) for b in bc if b["actual"])
            origins += [bn[0]["origin"], bn[-1]["origin"]]
            rows.append((evs[h], bn, bc))
        cal_pts, prev_pts, chosen = [], [], {"naive": 0, "recent_median": 0}
        for ev, bn, bc in rows:
            use = ev["chosen"]  # each series' own choice; pooling here is for reporting only
            chosen[use] += 1
            bt = bc if use == "recent_median" else bn
            cal_pts += walk_forward_intervals(bt)["points"]
            prev_pts += walk_forward_previous(bt)["points"]
        cal, prev = _summary(cal_pts), _summary(prev_pts)
        horizons.append({
            "days": h, "points": n, "first_origin": min(origins).isoformat() if origins else None,
            "last_origin": max(origins).isoformat() if origins else None,
            "mae_baseline_minor": _round(abs_b / n) if n else None, "mae_candidate_minor": _round(abs_c / n) if n else None,
            "mape_baseline_percent": _q2(ape_b / n * 100) if n else None, "mape_candidate_percent": _q2(ape_c / n * 100) if n else None,
            "candidate_chosen": chosen["recent_median"], "baseline_chosen": chosen["naive"],
            "calibrated": {"method": INTERVAL_METHOD, "points": cal["n"], "coverage_percent": cal["coverage_percent"], "mean_width_percent": cal["mean_width_percent"]},
            "previous": {"method": PREVIOUS_INTERVAL_METHOD, "points": prev["n"], "coverage_percent": prev["coverage_percent"], "mean_width_percent": prev["mean_width_percent"]},
        })
    return {"version": FORECAST_VERSION, "cutoff": _iso(cutoff), "basis": basis, "level_percent": INTERVAL_LEVEL,
            "products_evaluated": len(listings), "listings_evaluated": len(listings), "listings": listings, "insufficient": insufficient,
            "synthetic": bool(synthetic) and all(synthetic), "horizons": horizons,
            "note": ("Errors are pooled over every rolling-origin point (mean absolute error, MAPE). Each series chooses its own model from its own "
                     "backtest. Coverage is the share of walk-forward intervals that contained the observed price; "
                     "width is the interval's average size as a % of the prediction, so better coverage that comes only from wider intervals is visible. "
                     "Results on synthetic Demo data are not evidence of real-market performance.")}
