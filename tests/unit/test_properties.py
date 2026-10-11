"""Property-based tests: the parsers and the windowing hold for any input, not only for the examples."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from pyveoliaidf.aura import parse_response
from pyveoliaidf.convert import parse_index_reading, windows

# Text around a JSON object, which holds no brace.
NOISE = st.text(alphabet=st.characters(blacklist_characters="{}"), max_size=40)

JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=10),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=5), children, max_size=3),
    max_leaves=10,
)

DATES = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 1, 1))


@given(prefix=NOISE, suffix=NOISE, body=st.dictionaries(st.text(max_size=5), JSON_VALUES, max_size=4))
def test_parse_response_finds_the_object_among_noise(prefix: str, suffix: str, body: dict[str, object]) -> None:
    assert parse_response(prefix + json.dumps(body) + suffix) == body


@given(start=DATES, length=st.integers(min_value=1, max_value=1000), size=st.integers(min_value=1, max_value=120))
def test_windows_partition_the_range(start: date, length: int, size: int) -> None:
    end = start + timedelta(days=length - 1)

    result = windows(start, end, size)

    assert result[0][0] == start
    assert result[-1][1] == end
    assert all(last - first <= timedelta(days=size - 1) for first, last in result)
    assert all(first <= last for first, last in result)
    for (_, previous_end), (next_start, _) in zip(result, result[1:], strict=False):
        assert next_start == previous_end + timedelta(days=1)  # no gap and no overlap
    assert sum((last - first).days + 1 for first, last in result) == length


@given(
    index=st.decimals(min_value=0, max_value=10**7, places=3),
    moment=st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)),
)
def test_index_readings_round_trip(index: Decimal, moment: datetime) -> None:
    text = f"{index};{moment.strftime('%Y-%m-%d %H:%M:%S')}"

    parsed = parse_index_reading(text)

    assert parsed.index_m3 == index
    assert parsed.time == moment.replace(microsecond=0)
