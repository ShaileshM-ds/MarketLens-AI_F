"""History service: explicit UTC cutoff, no leakage, verified observations only, workspace isolation."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import p5_import, p5_row
from helpers import NOW
from marketlens_core.history import HistoryError, as_of, product_history

pytestmark = pytest.mark.integration
UTC = timezone.utc


def utc(day, hour=9):
    return f"2026-10-{day:02d}T{hour:02d}:00:00Z"


@pytest.fixture
def hist(p5):
    """MCL0001 has the p5 snapshot (timezone unknown) plus verified UTC history on Amazon and Flipkart."""
    rows = []
    for d in range(1, 31):
        if d in (10, 11):  # missing days stay gaps
            continue
        rows.append(p5_row("L-A", "Amazon", str(1500 - d), "60", timestamp=utc(d)))
        rows.append(p5_row("L-F", "Flipkart", str(1600 - 2 * d), "" if d == 20 else "40", timestamp=utc(d, 12)))
    rows.append(p5_row("L-A", "Amazon", "1400", "60", timestamp=utc(15, 18)))  # second observation that day
    p5_import(p5.db, p5.settings, rows, NOW, policy="require_utc", name="hist.csv")
    return p5


def H(p5, cutoff, **kw):
    return product_history(p5.db, "MCL0001", cutoff=cutoff, **{"window_days": 30, "basis": "base", **kw})


def test_series_uses_only_verified_observations_up_to_the_cutoff(hist):
    cutoff = datetime(2026, 10, 15, 12, tzinfo=UTC)
    h = H(hist, cutoff)
    assert h["status"] == "available" and h["currency"] == "INR"
    dates = [p["date"] for p in h["series"]]
    assert dates == sorted(dates) and dates[-1] == "2026-10-15"
    assert all(p["date"] <= "2026-10-15" for s in h["listings"] for p in s["points"])
    # 15 Oct: the 18:00 observation is after the 12:00 cutoff, so the 09:00 one (1485) counts; Flipkart 12:00 (1570).
    last = {s["marketplace"]: s["points"][-1] for s in h["listings"] if s["points"]}
    assert next(s for s in h["listings"] if s["marketplace"] == "Myntra")["points"] == []  # snapshot only
    assert last["Amazon"]["value_minor"] == 148500 and last["Flipkart"]["value_minor"] == 157000
    assert h["series"][-1]["value_minor"] == 148500 and h["series"][-1]["marketplaces"] == ["Amazon"]
    assert h["excluded"]["timezone_unknown"] == 3  # p5 snapshot never counts as history
    assert h["coverage"]["missing_dates"] == ["2026-10-10", "2026-10-11"]


def test_later_cutoff_sees_more_and_earlier_cutoff_never_sees_later_data(hist):
    early = H(hist, datetime(2026, 10, 5, 23, 59, 59, tzinfo=UTC))
    late = H(hist, datetime(2026, 10, 30, 23, 59, 59, tzinfo=UTC))
    assert early["series"][-1]["date"] == "2026-10-05"
    assert early["series"] == [p for p in late["series"] if p["date"] <= "2026-10-05"]
    same_day = H(hist, datetime(2026, 10, 15, 23, 59, 59, tzinfo=UTC))
    assert same_day["series"][-1]["value_minor"] == 140000  # daily value = lowest seen that day up to the cutoff


def test_windows_delivered_basis_and_store_filter(hist):
    cutoff = datetime(2026, 10, 30, 23, 59, 59, tzinfo=UTC)
    w7 = H(hist, cutoff, window_days=7)
    assert w7["window"]["start"].startswith("2026-10-24") and len(w7["series"]) == 7
    d = H(hist, cutoff, basis="delivered", marketplace="Flipkart")
    pts = {p["date"]: p["value_minor"] for p in d["series"]}
    assert "2026-10-20" not in pts  # unknown shipping is a gap, never zero
    assert pts["2026-10-21"] == (1600 - 42) * 100 + 4000
    with pytest.raises(HistoryError):
        H(hist, cutoff, window_days=45)


def test_cutoff_must_be_explicit_utc(hist):
    with pytest.raises(HistoryError):
        H(hist, datetime(2026, 10, 15, 12))  # naive
    with pytest.raises(HistoryError):
        as_of(hist.db, "MCL0001", at=datetime(2026, 10, 15))


def test_unavailable_without_verified_history(p5):
    h = H(p5, datetime(2026, 11, 5, tzinfo=UTC))
    assert h["status"] == "unavailable" and h["series"] == [] and h["excluded"]["timezone_unknown"] == 3
    assert "snapshot" in h["reason"].lower()


def test_time_machine_state_age_and_changes(hist):
    s = as_of(hist.db, "MCL0001", at=datetime(2026, 10, 12, 0, 0, tzinfo=UTC))
    a = next(x for x in s["listings"] if x["marketplace"] == "Amazon")
    assert a["observation"]["observed_at"].startswith("2026-10-09T09:00:00")  # 10 and 11 are missing
    assert a["age_seconds"] == int(timedelta(days=2, hours=15).total_seconds())
    assert a["previous"]["observed_at"].startswith("2026-10-08")
    assert a["changed_fields"] == ["price_minor"]
    assert "next" not in a  # nothing after the requested time is ever returned
    myntra = next(x for x in s["listings"] if x["marketplace"] == "Myntra")
    assert myntra["observation"] is None and myntra["reason"] == "No verified observation at or before this time."
    early = as_of(hist.db, "MCL0001", at=datetime(2026, 9, 1, tzinfo=UTC))
    assert all(x["observation"] is None for x in early["listings"])


def test_api_validation_and_workspace_isolation(hist):
    q = {"mode": "imported", "cutoff": "2026-10-15T12:00:00Z", "window": 30, "basis": "base"}
    r = hist.anon.get("/api/v1/products/MCL0001/history", params=q)
    assert r.status_code == 200 and r.json()["series"][-1]["date"] == "2026-10-15"
    assert hist.anon.get("/api/v1/products/MCL0001/history", params={**q, "cutoff": "2026-10-15T12:00:00"}).status_code == 422
    assert hist.anon.get("/api/v1/products/MCL0001/history", params={**q, "window": 45}).status_code == 422
    assert hist.anon.get("/api/v1/products/MCL0001/history", params={k: v for k, v in q.items() if k != "cutoff"}).status_code == 422
    assert hist.anon.get("/api/v1/products/MCL0001/history", params={**q, "mode": "demo"}).status_code == 404
    assert hist.anon.get("/api/v1/products/MCL0001/history", params={**q, "mode": "live"}).status_code == 409
    a = hist.anon.get("/api/v1/products/MCL0001/as-of", params={"mode": "imported", "at": "2026-10-12T00:00:00Z"})
    assert a.status_code == 200 and a.json()["requested_at"].startswith("2026-10-12T00:00:00")
    d = hist.anon.get("/api/v1/products/MCL0001", params={"mode": "imported"}).json()["price_history"]
    assert d["first_verified_at"].startswith("2026-10-01") and d["last_verified_at"].startswith("2026-10-30")
