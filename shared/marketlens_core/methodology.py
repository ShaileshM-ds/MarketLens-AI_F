"""The thresholds, weights and versions the Methodology page shows, read from the implementing modules so the
page can never drift from the code. Nothing here is computed from data."""

from . import advice, audit, dashboard, evidence, forecast, history, pricing, sync
from .alerts import engine, signals

SECTIONS = ["ingestion", "history", "prices", "detector", "score", "advice", "forecast", "memory", "sync", "audit", "dashboard", "alerts"]


def methodology() -> dict:
    return {
        "sections": SECTIONS,
        "history": {"windows": list(history.WINDOWS), "bases": list(history.BASES)},
        "pricing": {"discount_tolerance_points": pricing.MATERIAL_DIFFERENCE_POINTS},
        "evidence": {"version": evidence.EVIDENCE_VERSION, "min_days": evidence.MIN_DAYS, "savings_threshold": evidence.SAVINGS_THRESHOLD,
                     "full_savings": evidence.FULL_SAVINGS, "agreement_points": [evidence.AGREE_FULL, evidence.AGREE_NONE],
                     "reference_increase": evidence.REFERENCE_INCREASE, "stale_days": evidence.STALE_DAYS, "weights": evidence.WEIGHTS},
        "advice": {"version": advice.ADVICE_VERSION, "low_percentile": advice.LOW_PERCENTILE, "strong_savings": advice.STRONG_SAVINGS,
                   "strong_percentile": advice.STRONG_PERCENTILE, "fresh_hours": advice.FRESH_HOURS, "stale_days": advice.STALE_DAYS,
                   "missing_share": advice.MISSING_SHARE, "short_history_days": advice.SHORT_HISTORY_DAYS,
                   "expectation_horizon": advice.EXPECTATION_HORIZON},
        "forecast": {"version": forecast.FORECAST_VERSION, "horizons": list(forecast.HORIZONS), "models": forecast.MODELS,
                     "median_days": forecast.MEDIAN_DAYS, "min_train_days": forecast.MIN_TRAIN_DAYS, "min_origins": forecast.MIN_ORIGINS,
                     "max_origins": forecast.MAX_ORIGINS, "min_improvement_percent": forecast.MIN_IMPROVEMENT,
                     "interval_level_percent": forecast.INTERVAL_LEVEL, "interval_method": forecast.INTERVAL_METHOD,
                     "min_residuals": forecast.MIN_RESIDUALS, "lookback_days": forecast.LOOKBACK_DAYS, "stale_days": forecast.STALE_DAYS},
        "memory": {"drop_percent": forecast.DROP * 100, "return_within_percent": forecast.RETURN_WITHIN * 100,
                   "further_percent": forecast.FURTHER * 100, "days": list(forecast.MEMORY_DAYS), "baseline_days": forecast.MIN_TRAIN_DAYS},
        "sync": {"version": sync.SYNC_VERSION, "change_percent": sync.CHANGE_PERCENT, "max_gap_days": sync.MAX_GAP_DAYS,
                 "match_days": sync.MATCH_DAYS, "min_days": sync.MIN_DAYS, "min_matches": sync.MIN_MATCHES, "min_share": sync.MIN_SHARE,
                 "stale_days": sync.STALE_DAYS, "benign": sync.BENIGN},
        "audit": {"version": audit.AUDIT_VERSION, "urgency_min_days": audit.URGENCY_MIN_DAYS, "low_stock": audit.LOW_STOCK,
                  "rules": [{"rule_id": k, **v} for k, v in audit.RULES.items()]},
        "dashboard": {"version": dashboard.DASHBOARD_VERSION, "max_products": dashboard.MAX_PRODUCTS},
        "alerts": {k: v for k, v in signals.TYPES.items()},
        "alert_rules": {"new_low_lookback_days": signals.NEW_LOW_LOOKBACK_DAYS, "new_low_min_days": signals.NEW_LOW_MIN_DAYS,
                        "switch_fresh_days": signals.SWITCH_FRESH_DAYS, "default_min_score": signals.DEFAULT_MIN_SCORE,
                        "min_score_range": list(signals.MIN_SCORE_RANGE), "window_days": signals.WINDOW, "event_key": "sha256(rule|event)[:24]",
                        "batch": engine.BATCH},
    }
