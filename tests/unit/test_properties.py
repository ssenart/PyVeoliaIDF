"""Property-based tests: the parsers and the unit conversion hold for any input, not only for the examples."""

import json
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from pyveoliaidf.aura import parse_response
from pyveoliaidf.client import to_liters

# Text around a JSON object, which holds no brace.
NOISE = st.text(alphabet=st.characters(blacklist_characters="{}"), max_size=40)

JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=10),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=5), children, max_size=3),
    max_leaves=10,
)


@given(prefix=NOISE, suffix=NOISE, body=st.dictionaries(st.text(max_size=5), JSON_VALUES, max_size=4))
def test_parse_response_finds_the_object_among_noise(prefix: str, suffix: str, body: dict[str, object]) -> None:
    assert parse_response(prefix + json.dumps(body) + suffix) == body


@given(liters=st.integers(min_value=0, max_value=10**9))
def test_liters_survive_a_round_trip_through_cubic_meters(liters: int) -> None:
    assert to_liters(Decimal(liters) / 1000) == liters


@given(first=st.integers(min_value=0, max_value=10**9), second=st.integers(min_value=0, max_value=10**9))
def test_conversion_keeps_the_order(first: int, second: int) -> None:
    low, high = sorted((first, second))

    assert to_liters(Decimal(low) / 1000) <= to_liters(Decimal(high) / 1000)
