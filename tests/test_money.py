import pytest

from marketlens_core.money import MoneyError, minor_digits, to_minor_units


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1380", 138000),
        ("0", 0),
        ("1380.5", 138050),
        ("1380.50", 138050),
        ("0.29", 29),  # float arithmetic would give 28
        ("0.1", 10),
        ("1380.500", 138050),  # trailing zeros are not extra precision
        ("  60 ", 6000),
    ],
)
def test_inr_rupees_to_minor_units(text, expected):
    assert to_minor_units(text, "INR") == expected


def test_zero_decimal_currency():
    assert minor_digits("JPY") == 0
    assert to_minor_units("1380", "JPY") == 1380
    with pytest.raises(MoneyError, match="decimal places"):
        to_minor_units("13.5", "JPY")


@pytest.mark.parametrize(
    "text,fragment",
    [
        ("abc", "not a plain amount"),
        ("1,380", "not a plain amount"),
        ("₹1380", "not a plain amount"),
        ("1e3", "not a plain amount"),
        ("-5", "negative"),
        ("12.345", "decimal places"),
        ("", "not a plain amount"),
    ],
)
def test_invalid_amounts_have_plain_reasons(text, fragment):
    with pytest.raises(MoneyError, match=fragment):
        to_minor_units(text, "INR", field="price")


def test_reason_names_the_field_and_value():
    with pytest.raises(MoneyError) as exc:
        to_minor_units("abc", "INR", field="price")
    assert "price 'abc'" in str(exc.value)


def test_unknown_currency_rejected():
    with pytest.raises(MoneyError, match="not supported"):
        minor_digits("XYZ")
