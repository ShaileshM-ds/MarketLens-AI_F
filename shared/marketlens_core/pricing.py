"""Pricing and discount rules, shared by the API (and any future worker use).

All money is integer minor units. Percentages are computed with Decimal and
rounded half-up to 2 decimals. Nothing here subtracts coupons or payment offers,
treats unknown shipping as zero, or recommends an offer reported unavailable.
"""

from decimal import ROUND_HALF_UP, Decimal

MATERIAL_DIFFERENCE_POINTS = 0.5  # same tolerance as the importer's discount_mismatch check
_CENT = Decimal("0.01")


def _minor(value, field: str):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer number of minor units, got {value!r}")
    return value


def _pct(d: Decimal) -> float:
    return float(d.quantize(_CENT, rounding=ROUND_HALF_UP))


def delivered_price(price_minor, shipping_minor, shipping_known: bool):
    """Base price + known shipping. None unless shipping is known."""
    price = _minor(price_minor, "price")
    shipping = _minor(shipping_minor, "shipping")
    if price is None or not shipping_known or shipping is None:
        return None
    return price + shipping


def _reduction(price: int | None, reference: int | None) -> Decimal | None:
    if price is None or reference is None or reference == 0:
        return None
    return (Decimal(reference - price) / Decimal(reference)) * 100


def reference_reduction_percent(price_minor, reference_minor):
    """(reference − price) / reference × 100. Negative when the price is above the reference."""
    r = _reduction(_minor(price_minor, "price"), _minor(reference_minor, "reference price"))
    return None if r is None else _pct(r)


def discount_analysis(price_minor, reference_minor, advertised_percent) -> dict:
    """Advertised discount vs the reduction from the seller-provided reference price."""
    price = _minor(price_minor, "price")
    reference = _minor(reference_minor, "reference price")
    calc = _reduction(price, reference)
    adv = None if advertised_percent is None else Decimal(str(advertised_percent))
    diff = None if (calc is None or adv is None) else (adv - calc.quantize(_CENT, rounding=ROUND_HALF_UP))

    if price is None:
        status, note = "no_price", "No current price, so the discount can't be checked."
    elif calc is None:
        status, note = "no_reference", "No reference price was supplied, so the reduction can't be calculated."
    elif price > reference:
        status, note = "price_above_reference", "The listed price is above the seller-provided reference price."
    elif adv is None:
        status, note = "no_advertised", "No advertised discount was supplied; only the calculated reduction is shown."
    elif abs(diff) <= Decimal(str(MATERIAL_DIFFERENCE_POINTS)):
        status, note = "consistent", "The advertised discount matches the reduction from the reference price (within 0.5 points)."
    else:
        status = "differs"
        note = (
            f"The advertised discount differs from the reference-price reduction by {abs(_pct(diff)):.2f} points. "
            "This can come from rounding, a different reference price or a promotion not recorded here."
        )
    return {
        "reference_price_minor": reference,
        "price_minor": price,
        "advertised_percent": None if adv is None else _pct(adv),
        "calculated_percent": None if calc is None else _pct(calc),
        "difference_points": None if diff is None else _pct(diff),
        "material": diff is not None and abs(diff) > Decimal(str(MATERIAL_DIFFERENCE_POINTS)),
        "status": status,
        "note": note,
    }


def _available_exclusion(o: dict) -> str | None:
    if o.get("price_minor") is None:
        return "No current price"
    if "stock_availability_contradiction" in (o.get("flags") or []):
        return "Availability and reported stock quantity disagree"
    cls = o.get("availability_class")
    if cls == "out_of_stock":
        return "Reported out of stock"
    if cls not in ("in_stock", "limited_stock"):
        return "Availability not reported"
    return None


def _designation(candidates: list[tuple[int, dict]], currency, note: str, **extra) -> dict:
    if not candidates:
        return {"amount_minor": None, "currency": currency, "listing_ids": [], "marketplaces": [], "considered_count": 0, "note": note, **extra}
    low = min(a for a, _ in candidates)
    ties = sorted((o for a, o in candidates if a == low), key=lambda o: o["listing_id"])
    return {
        "amount_minor": low,
        "currency": currency,
        "listing_ids": [o["listing_id"] for o in ties],
        "marketplaces": sorted({o["marketplace"] for o in ties}),
        "considered_count": len(candidates),
        "note": note,
        **extra,
    }


def _uncertainty(low: int | None, pool: list[dict]) -> tuple[bool, str]:
    unknown = [o for o in pool if o.get("price_minor") is not None and not o.get("shipping_known")]
    risky = [o for o in unknown if low is None or o["price_minor"] < low]
    if risky and low is not None:
        return False, (
            f" {len(risky)} listing(s) with unknown shipping have a lower base price, "
            "so the cheapest delivered price overall can't be determined."
        )
    return True, ""


def lowest_designations(offers: list[dict]) -> dict:
    """Three clearly different 'lowest' answers. Ties list every tied listing in listing-ID order."""
    priced = [o for o in offers if o.get("price_minor") is not None]
    currencies = sorted({o["currency"] for o in priced if o.get("currency")})
    if len(currencies) > 1:
        note = f"Listings use different currencies ({', '.join(currencies)}); prices aren't compared across currencies."
        empty = lambda **x: _designation([], None, note, **x)  # noqa: E731
        return {
            "currency": None,
            "lowest_listed": empty(certain_overall=False),
            "lowest_confirmed_delivered": empty(certain_overall=False),
            "lowest_confirmed_delivered_available": empty(certain_overall=False, excluded=[]),
        }
    currency = currencies[0] if currencies else None

    listed = _designation(
        [(o["price_minor"], o) for o in priced],
        currency,
        "Lowest base listing price across all listings, before shipping. Availability is not considered.",
        certain_overall=True,
    )

    def delivered(o):
        return delivered_price(o.get("price_minor"), o.get("shipping_minor"), bool(o.get("shipping_known")))

    confirmed = [(delivered(o), o) for o in priced if delivered(o) is not None]
    low = min((a for a, _ in confirmed), default=None)
    certain, extra = _uncertainty(low, priced)
    base_note = (
        "Base price plus known shipping, across all listings including ones reported unavailable."
        if confirmed
        else "No listing has a confirmed delivered price."
    )
    lowest_delivered = _designation(confirmed, currency, base_note + extra, certain_overall=certain)

    excluded, avail_pool = [], []
    for o in offers:
        why = _available_exclusion(o)
        if why:
            excluded.append({"listing_id": o["listing_id"], "marketplace": o.get("marketplace"), "reason": why})
        else:
            avail_pool.append(o)
    excluded.sort(key=lambda x: x["listing_id"])
    avail_confirmed = [(delivered(o), o) for o in avail_pool if delivered(o) is not None]
    a_low = min((a for a, _ in avail_confirmed), default=None)
    a_certain, a_extra = _uncertainty(a_low, avail_pool)
    a_note = (
        "Lowest confirmed delivered price among listings reported in stock or limited stock in the imported snapshot, without stock warnings."
        if avail_confirmed
        else "No listing reported available has a confirmed delivered price."
    )
    lowest_available = _designation(avail_confirmed, currency, a_note + a_extra, certain_overall=a_certain, excluded=excluded)

    return {
        "currency": currency,
        "lowest_listed": listed,
        "lowest_confirmed_delivered": lowest_delivered,
        "lowest_confirmed_delivered_available": lowest_available,
    }
