"""Pure explorer logic: availability classes, current-observation selection, offer pricing."""

from datetime import datetime, timezone

from marketlens_core.explorer import availability_class, offer_view, select_current


def obs(**kw):
    base = {
        "_id": "o1",
        "listing_id": "L1",
        "source_timestamp": "2026-11-04T10:30:00",
        "observed_at": None,
        "timestamp_quality": "timezone_unknown",
        "history_eligible": False,
        "currency": "INR",
        "price_minor": 138000,
        "reference_price_minor": 160000,
        "shipping_minor": 6000,
        "shipping_known": True,
        "coupon_discount_minor": 30000,
        "payment_offer": "Eligible bank card offer: ₹500",
        "availability": "In Stock",
        "stock_quantity": 8,
        "flags": [],
        "seller_rating": 4.3,
        "product_rating": 3.5,
    }
    base.update(kw)
    return base


def utc(day, hour=10):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def test_availability_classes():
    assert availability_class("In Stock") == "in_stock"
    assert availability_class("Limited Stock") == "limited_stock"
    assert availability_class("Out of Stock") == "out_of_stock"
    assert availability_class(None) == "unknown"
    assert availability_class("Ships in 3 weeks") == "unknown"


def test_single_timezone_unknown_snapshot_is_current_but_labelled():
    cur, basis = select_current([obs()])
    assert cur["_id"] == "o1"
    assert basis == "single_snapshot_timezone_unknown"


def test_several_timezone_unknown_snapshots_are_not_ordered():
    a = obs(_id="a", source_timestamp="2026-11-04T10:30:00")
    b = obs(_id="b", source_timestamp="2026-11-05T10:30:00")
    cur, basis = select_current([a, b])
    assert cur is None
    assert basis == "ambiguous_unordered_snapshots"


def test_latest_verified_utc_observation_wins():
    snap = obs(_id="snap")
    early = obs(_id="early", observed_at=utc(4), timestamp_quality="utc", history_eligible=True)
    late = obs(_id="late", observed_at=utc(5), timestamp_quality="utc", history_eligible=True, price_minor=130000)
    cur, basis = select_current([snap, late, early])
    assert cur["_id"] == "late"
    assert basis == "latest_verified_utc"


def test_no_observations():
    assert select_current([]) == (None, "no_observation")


def test_offer_view_known_total_and_conditional_offers_not_subtracted():
    v = offer_view(obs())
    assert v["price_minor"] == 138000
    assert v["shipping_minor"] == 6000
    assert v["total_minor"] == 144000
    assert isinstance(v["total_minor"], int)
    assert v["coupon_discount_minor"] == 30000  # shown, never subtracted
    assert v["free_shipping"] is False


def test_offer_view_free_and_unknown_shipping():
    free = offer_view(obs(shipping_minor=0))
    assert free["free_shipping"] is True and free["total_minor"] == 138000
    unknown = offer_view(obs(shipping_minor=None, shipping_known=False))
    assert unknown["free_shipping"] is False
    assert unknown["total_minor"] is None
    assert "shipping_unknown" in [w["code"] for w in unknown["warnings"]]


def test_offer_view_small_amounts_stay_exact():
    v = offer_view(obs(price_minor=29, shipping_minor=1))
    assert v["total_minor"] == 30


def test_offer_view_flags_contradiction_and_not_purchasable():
    v = offer_view(obs(availability="Out of Stock", stock_quantity=25, flags=["stock_availability_contradiction"]))
    codes = [w["code"] for w in v["warnings"]]
    assert "stock_availability_contradiction" in codes
    msg = next(w["message"] for w in v["warnings"] if w["code"] == "stock_availability_contradiction")
    assert msg == "Availability and reported stock quantity disagree."
    assert v["purchasable"] is False
    assert v["availability_class"] == "out_of_stock"
    assert v["stock_quantity"] == 25  # never corrected


def test_offer_view_timezone_warning():
    codes = [w["code"] for w in offer_view(obs())["warnings"]]
    assert "timezone_unknown" in codes
