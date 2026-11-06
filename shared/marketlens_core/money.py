"""Decimal-safe conversion of major-unit amounts (e.g. rupees) to integer minor units."""

import re
from decimal import Decimal

# ISO 4217 minor-unit digits for currencies we accept. Extend deliberately.
CURRENCY_MINOR_DIGITS = {
    "INR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AED": 2,
    "SGD": 2,
    "JPY": 0,
    "KRW": 0,
}

_PLAIN_AMOUNT = re.compile(r"^\d+(\.\d+)?$")


class MoneyError(ValueError):
    pass


def minor_digits(currency: str) -> int:
    code = (currency or "").strip().upper()
    if code not in CURRENCY_MINOR_DIGITS:
        raise MoneyError(f"currency '{currency}' is not supported")
    return CURRENCY_MINOR_DIGITS[code]


def to_minor_units(text: str, currency: str, field: str = "amount") -> int:
    """'1380' INR -> 138000. Never uses floats. Raises MoneyError with a plain reason."""
    s = (text or "").strip()
    if s.startswith("-"):
        raise MoneyError(f"{field} '{text}' is negative; amounts cannot be negative")
    if not _PLAIN_AMOUNT.match(s):
        raise MoneyError(
            f"{field} '{text}' is not a plain amount (use digits with an optional decimal point, "
            "without commas or currency symbols)"
        )
    digits = minor_digits(currency)
    fraction = s.split(".", 1)[1] if "." in s else ""
    if len(fraction.rstrip("0")) > digits:
        raise MoneyError(f"{field} '{text}' has more decimal places than {currency.upper()} allows ({digits})")
    return int(Decimal(s).scaleb(digits))
