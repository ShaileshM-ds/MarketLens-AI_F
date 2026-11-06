"""Pricing and discount rules (pure). Amounts are integer minor units."""

import pytest

from marketlens_core.pricing import (
    MATERIAL_DIFFERENCE_POINTS,
    delivered_price,
    discount_analysis,
    lowest_designations,
    reference_reduction_percent,
)


# ---------- delivered price ----------
def test_delivered_price_known_free_and_unknown_shipping():
    assert delivered_price(138000, 6000, True) == 144000
    assert delivered_price(148000, 0, True) == 148000  # known free shipping
    assert delivered_price(138000, None, False) is None  # unknown is never zero
    assert delivered_price(138000, 0, False) is None  # not known -> not confirmed, even if a 0 slipped in
    assert delivered_price(None, 6000, True) is None
    assert delivered_price(29, 1, True) == 30
    assert isinstance(delivered_price(138000, 6000, True), int)


@pytest.mark.parametrize("bad", [-1, 1.5, "100", True])
def test_monetary_inputs_must_be_non_negative_integers(bad):
    with pytest.raises(ValueError):
        delivered_price(bad, 0, True)
    with pytest.raises(ValueError):
        delivered_price(100, bad, True)
    with pytest.raises(ValueError):
        reference_reduction_percent(bad, 100)


# ---------- reference-price reduction ----------
def test_reference_reduction_is_decimal_exact_and_half_up():
    assert reference_reduction_percent(138000, 160000) == 13.75
    assert reference_reduction_percent(137000, 160000) == 14.38  # 14.375 rounds half-up
    assert reference_reduction_percent(1, 3) == 66.67
    assert reference_reduction_percent(29, 100) == 71.0
    assert reference_reduction_percent(160000, 160000) == 0.0


def test_reference_reduction_missing_zero_or_below_price():
    assert reference_reduction_percent(138000, None) is None
    assert reference_reduction_percent(138000, 0) is None
    assert reference_reduction_percent(None, 160000) is None
    assert reference_reduction_percent(170000, 160000) == -6.25  # price above reference


# ---------- advertised vs calculated ----------
def test_consistent_advertised_discount():
    a = discount_analysis(138000, 160000, 13.75)
    assert a["status"] == "consistent"
    assert a["calculated_percent"] == 13.75 and a["advertised_percent"] == 13.75
    assert a["difference_points"] == 0.0 and a["material"] is False


def test_material_difference_is_flagged_without_accusation():
    a = discount_analysis(138000, 160000, 20)
    assert a["status"] == "differs" and a["material"] is True
    assert a["difference_points"] == 6.25
    assert "mislead" not in a["note"].lower() and "fake" not in a["note"].lower()
    assert MATERIAL_DIFFERENCE_POINTS == 0.5
    near = discount_analysis(138000, 160000, 14.2)  # 0.45 points: within tolerance
    assert near["status"] == "consistent" and near["difference_points"] == 0.45


def test_missing_promotion_or_reference():
    a = discount_analysis(138000, 160000, None)
    assert a["status"] == "no_advertised" and a["calculated_percent"] == 13.75 and a["difference_points"] is None
    b = discount_analysis(138000, None, 13.75)
    assert b["status"] == "no_reference" and b["calculated_percent"] is None and b["difference_points"] is None
    c = discount_analysis(170000, 160000, 5)
    assert c["status"] == "price_above_reference" and c["calculated_percent"] == -6.25
    d = discount_analysis(None, 160000, 10)
    assert d["status"] == "no_price"


# ---------- lowest designations ----------
def offer(lid, market, price, shipping=0, known=True, cls="in_stock", flags=(), currency="INR", coupon=None):
    return {
        "listing_id": lid,
        "marketplace": market,
        "currency": currency,
        "price_minor": price,
        "shipping_minor": shipping if known else None,
        "shipping_known": known,
        "availability_class": cls,
        "flags": list(flags),
        "coupon_discount_minor": coupon,
    }


MCL = [
    offer("A", "Amazon", 138000, 6000),
    offer("F", "Flipkart", 137000, 6000),
    offer("M", "Myntra", 148000, 0),
]


def test_three_designations_for_a_typical_product():
    d = lowest_designations(MCL)
    assert d["lowest_listed"]["amount_minor"] == 137000 and d["lowest_listed"]["listing_ids"] == ["F"]
    assert d["lowest_confirmed_delivered"]["amount_minor"] == 143000
    assert d["lowest_confirmed_delivered"]["certain_overall"] is True
    assert d["lowest_confirmed_delivered_available"]["amount_minor"] == 143000
    assert d["lowest_confirmed_delivered_available"]["marketplaces"] == ["Flipkart"]
    assert d["currency"] == "INR"


def test_ties_are_all_reported_in_stable_order():
    d = lowest_designations([offer("Z", "Myntra", 100000, 0), offer("B", "Amazon", 95000, 5000), offer("C", "Flipkart", 120000)])
    assert d["lowest_confirmed_delivered"]["listing_ids"] == ["B", "Z"]
    assert d["lowest_confirmed_delivered"]["marketplaces"] == ["Amazon", "Myntra"]


def test_unknown_shipping_can_make_the_overall_cheapest_uncertain():
    d = lowest_designations([offer("A", "Amazon", 100000, known=False), offer("F", "Flipkart", 110000, 5000)])
    cd = d["lowest_confirmed_delivered"]
    assert cd["amount_minor"] == 115000 and cd["certain_overall"] is False
    assert "unknown shipping" in cd["note"].lower()
    assert d["lowest_listed"]["amount_minor"] == 100000
    # An unknown-shipping offer whose base price is already higher can't be cheaper.
    d2 = lowest_designations([offer("A", "Amazon", 120000, known=False), offer("F", "Flipkart", 110000, 5000)])
    assert d2["lowest_confirmed_delivered"]["certain_overall"] is True


def test_unavailable_and_contradictory_offers_are_not_recommended():
    offers = [
        offer("O", "Amazon", 90000, 0, cls="out_of_stock"),
        offer("C", "Myntra", 91000, 0, cls="out_of_stock", flags=["stock_availability_contradiction"]),
        offer("I", "Flipkart", 100000, 0),
    ]
    d = lowest_designations(offers)
    assert d["lowest_confirmed_delivered"]["listing_ids"] == ["O"]  # cheapest overall, labelled as such
    avail = d["lowest_confirmed_delivered_available"]
    assert avail["listing_ids"] == ["I"]
    excluded = {x["listing_id"]: x["reason"] for x in avail["excluded"]}
    assert excluded == {"O": "Reported out of stock", "C": "Availability and reported stock quantity disagree"}


def test_coupons_and_missing_prices_do_not_change_totals():
    d = lowest_designations([offer("A", "Amazon", 100000, 0, coupon=30000), offer("N", "Myntra", None)])
    assert d["lowest_confirmed_delivered"]["amount_minor"] == 100000
    assert d["lowest_listed"]["listing_ids"] == ["A"]


def test_nothing_confirmed_or_mixed_currencies():
    d = lowest_designations([offer("A", "Amazon", 100000, known=False)])
    assert d["lowest_confirmed_delivered"]["amount_minor"] is None
    assert "no listing has a confirmed delivered price" in d["lowest_confirmed_delivered"]["note"].lower()
    m = lowest_designations([offer("A", "Amazon", 100000), offer("U", "Flipkart", 1000, currency="USD")])
    for key in ("lowest_listed", "lowest_confirmed_delivered", "lowest_confirmed_delivered_available"):
        assert m[key]["amount_minor"] is None and "currenc" in m[key]["note"].lower()
    assert m["currency"] is None
    assert lowest_designations([])["lowest_listed"]["amount_minor"] is None
