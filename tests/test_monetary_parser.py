import pytest
from polla_app.sources.pozos import _parse_millones_to_clp
from polla_app.exceptions import ParseError

@pytest.mark.parametrize("raw, expected", [
    ("690", 690_000_000),
    ("$ 690", 690_000_000),
    ("4.300", 4_300_000_000),
    ("4,75", 4_750_000),
    ("1.234,56", 1_234_560_000),
    ("4300", 4_300_000_000),
    ("$ 4.300", 4_300_000_000),
    ("0,5", 500_000),
    ("4.300 MM", 4_300_000_000),
    ("4,3 M", 4_300_000),
    ("1.000.000 Mil", 1_000_000_000), # Mil as thousands of Millions (not used much, but testing suffix)
    ("7500", 7_500_000_000),
])
def test_parse_millones_to_clp_valid(raw, expected):
    assert _parse_millones_to_clp(raw) == expected

@pytest.mark.parametrize("raw", [
    "",
    " ",
    "$",
    "abc",
    "1.2.3.4", # Ambiguous
])
def test_parse_millones_to_clp_invalid(raw):
    with pytest.raises(ParseError):
        _parse_millones_to_clp(raw)

def test_parse_millones_to_clp_absolute_large():
    # If the value is already in the billions range absolute, it should be treated as such
    # However, the current contract is Millions context.
    # We'll see how the implementation handles "1.234.567.890"
    pass
