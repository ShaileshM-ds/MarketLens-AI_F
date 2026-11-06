"""Pure mapping of one supplied CSV row (no database)."""

from helpers import SAMPLE_ROW, ctx, make_parsed, snapshot_config
from marketlens_core.importing.rows import map_row


def map_one(overrides=None, **config_overrides):
    row = {**SAMPLE_ROW, **(overrides or {})}
    parsed = make_parsed([row])
    return map_row(parsed.rows[0], snapshot_config(parsed.columns, **config_overrides), ctx())


def reason_codes(result):
    return [r.code for r in result.reasons]


def test_money_fields_become_integer_minor_units():
    r = map_one()
    assert r.ok, r.reasons
    o = r.observation
    assert o["price_minor"] == 138000
    assert o["reference_price_minor"] == 160000
    assert o["shipping_minor"] == 6000 and o["shipping_known"] is True
    assert o["coupon_discount_minor"] == 0
    assert o["currency"] == "INR"
    assert all(isinstance(o[k], int) for k in ("price_minor", "reference_price_minor", "shipping_minor"))


def test_conditional_offers_never_reduce_price():
    r = map_one({"coupon_discount": "300", "payment_offer": "Eligible bank card offer: ₹500"})
    o = r.observation
    assert o["price_minor"] == 138000
    assert o["coupon_discount_minor"] == 30000
    assert o["payment_offer"] == "Eligible bank card offer: ₹500"
    assert o["offers_applied_to_price"] is False


def test_blank_shipping_is_unknown_and_zero_is_known_free():
    blank = map_one({"shipping_cost": ""}).observation
    assert blank["shipping_minor"] is None and blank["shipping_known"] is False
    free = map_one({"shipping_cost": "0"}).observation
    assert free["shipping_minor"] == 0 and free["shipping_known"] is True


def test_discount_stays_advertised_percent():
    assert map_one().observation["advertised_discount_percent"] == 13.75


def test_timezone_unknown_timestamp_preserved_and_not_history_eligible():
    o = map_one().observation
    assert o["source_timestamp"] == "2026-11-04T10:30:00"
    assert o["observed_at"] is None
    assert o["timestamp_quality"] == "timezone_unknown"
    assert o["history_eligible"] is False


def test_observation_identity_is_listing_plus_source_timestamp():
    assert map_one().observation["_id"] == "obs1|AMA-CLO-LIST-000001|source-time:2026-11-04T10:30:00"


def test_provenance_and_original_row_kept():
    r = map_one()
    o = r.observation
    assert o["synthetic"] is True
    assert o["source"] == "Generated for project demonstration"
    assert o["source_type"] == "Synthetic"
    assert o["source_label"] == "Generated for project demonstration"
    p = o["provenance"]
    assert p["ingestion_run_id"] == "run-test"
    assert p["source_file_id"] == "file-test"
    assert p["raw_source_ref"] == "file-test:sample.csv#row=1"
    assert p["row_number"] == 1
    assert p["schema_version"] == "1"
    assert p["ingested_at"] is not None
    assert o["raw"] == SAMPLE_ROW
    for doc in (r.product, r.offer, r.review):
        assert doc["synthetic"] is True and doc["provenance"]["ingestion_run_id"] == "run-test"


def test_brand_size_colour_never_guessed_from_name():
    p = map_one().product
    assert "Nike" in p["name"] and "Size S" in p["name"] and "Black" in p["name"]
    assert p["brand"] is None and p["size"] is None and p["colour"] is None


def test_category_mapped_and_original_kept():
    p = map_one().product
    assert p["category"] == "mens-clothing"
    assert p["source_category"] == "T-Shirts"


def test_unmapped_category_rejected():
    r = map_one({"category": "Socks"})
    assert not r.ok and "unmapped_category" in reason_codes(r)
    assert "Socks" in r.reasons[0].message


def test_review_linked_to_product_listing_and_observation():
    r = map_one()
    rev = r.review
    assert rev["product_id"] == "MCL0001"
    assert rev["listing_id"] == "AMA-CLO-LIST-000001"
    assert rev["observation_id"] == r.observation["_id"]
    assert rev["review_rating"] == 3
    assert rev["text"] == SAMPLE_ROW["review"]
    assert rev["review_source"] == "Synthetic (generated sample review)"
    assert rev["synthetic"] is True
    assert rev["reviewer_name"] is None and rev["review_date"] is None


def test_product_rating_stays_per_listing_and_separate_from_review_rating():
    r = map_one()
    assert r.observation["product_rating"] == 3.5
    assert r.review["review_rating"] == 3
    assert "product_rating" not in r.review
    assert "product_rating" not in r.product


def test_no_review_when_review_columns_blank():
    assert map_one({"review": "", "rating": ""}).review is None


def test_invalid_review_rating_rejected():
    r = map_one({"rating": "7"})
    assert not r.ok and "invalid_number" in reason_codes(r)


def test_condition_and_preserved_fields():
    r = map_one()
    o = r.observation
    assert o["condition"] == "New" and r.offer["condition"] == "New"
    assert o["delivery_information"] == "Delivery in 2-4 days"
    assert o["urgency_message"] == "Deal ends soon (synthetic example)"
    assert o["seller_location"] == "Bengaluru, Karnataka"
    assert o["seller_rating"] == 4.3
    assert o["stock_quantity"] == 8
    assert o["source_last_updated"] == "2026-11-04T10:30:00"


def test_blank_stock_preserved_as_unknown():
    r = map_one({"stock_quantity": ""})
    assert r.ok and r.observation["stock_quantity"] is None and r.warnings == []


def test_fractional_or_negative_stock_rejected():
    for bad in ("8.5", "-1"):
        r = map_one({"stock_quantity": bad})
        assert not r.ok and "invalid_number" in reason_codes(r)
        assert "whole number" in r.reasons[0].message


def test_stock_contradiction_flagged_not_corrected():
    r = map_one({"availability": "Out of Stock", "stock_quantity": "25.0"})
    assert r.ok
    assert [w.code for w in r.warnings] == ["stock_availability_contradiction"]
    o = r.observation
    assert o["availability"] == "Out of Stock" and o["stock_quantity"] == 25
    assert o["flags"] == ["stock_availability_contradiction"]
    r2 = map_one({"availability": "In Stock", "stock_quantity": "0"})
    assert [w.code for w in r2.warnings] == ["stock_availability_contradiction"]


def test_stock_contradiction_quarantined_in_history_files():
    for availability, stock in (("Out of Stock", "25"), ("In Stock", "0")):
        r = map_one({"timestamp": "2026-11-05T10:30:00Z", "availability": availability, "stock_quantity": stock}, timestamp_policy="require_utc")
        assert not r.ok
        assert reason_codes(r) == ["stock_availability_contradiction"]
        assert f"Availability is '{availability}'" in r.reasons[0].message
        assert "history" in r.reasons[0].message


def test_consistent_or_blank_stock_accepted_in_history_files():
    for availability, stock in (("Out of Stock", "0"), ("In Stock", "25"), ("Out of Stock", "")):
        r = map_one({"timestamp": "2026-11-05T10:30:00Z", "availability": availability, "stock_quantity": stock}, timestamp_policy="require_utc")
        assert r.ok, r.reasons


def test_invalid_price_rejected_with_plain_reason():
    r = map_one({"price": "abc"})
    assert not r.ok
    assert r.reasons[0].code == "invalid_money"
    assert "price 'abc'" in r.reasons[0].message


def test_blank_required_fields_rejected():
    r = map_one({"listing_id": "", "price": ""})
    messages = [x.message for x in r.reasons]
    assert "listing ID is blank" in messages
    assert "price is blank" in messages


def test_ids_preserved_exactly():
    r = map_one({"seller_id": "clsel00001", "listing_id": "AMA-clo-LIST-000001"})
    assert r.offer["seller_id"] == "clsel00001"
    assert r.offer["_id"] == "AMA-clo-LIST-000001"


def test_placeholder_image_uses_local_generic():
    img = map_one().product["image"]
    assert img["kind"] == "generic_placeholder"
    assert img["source_url"].startswith("https://placehold.co/")


def test_provenance_required():
    r = map_one({"source_type": ""})
    assert not r.ok and "provenance_unknown" in reason_codes(r)
    declared = map_one({"source_type": ""}, declare_synthetic=True)
    assert declared.ok and declared.observation["synthetic"] is True


def test_real_source_type_is_not_synthetic():
    r = map_one({"source_type": "Observed", "review_source": "Customer"})
    assert r.observation["synthetic"] is False
    assert r.review["synthetic"] is False
