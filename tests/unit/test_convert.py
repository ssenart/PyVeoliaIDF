from datetime import date, datetime
from decimal import Decimal

import pytest

from pyveoliaidf.convert import (
    build_history,
    flag_meter_changes,
    parse_index_reading,
    to_contract,
    to_party,
    to_reading,
    windows,
)
from pyveoliaidf.errors import UnexpectedResponseError
from pyveoliaidf.model import Meter, Reading, Step
from pyveoliaidf.veolia_models import VeoliaConsumptionRecord, VeoliaConsumptionResponse, VeoliaContractDetails
from tests.unit.helpers import consumption, contract_details, record

METER = Meter(number="X1", point_id="123", meter_token="t1", point_token="t2")
NOW = datetime(2026, 10, 11, 12, 0)


def response(records: list[dict[str, object]], **top: object) -> VeoliaConsumptionResponse:
    return VeoliaConsumptionResponse.model_validate(consumption(records, **top))


class TestWindows:
    def test_one_window_when_the_range_is_short(self) -> None:
        assert windows(date(2026, 1, 1), date(2026, 1, 10), 90) == [(date(2026, 1, 1), date(2026, 1, 10))]

    def test_consecutive_windows_that_cover_the_range_exactly(self) -> None:
        result = windows(date(2026, 1, 1), date(2026, 1, 10), 4)

        assert result == [
            (date(2026, 1, 1), date(2026, 1, 4)),
            (date(2026, 1, 5), date(2026, 1, 8)),
            (date(2026, 1, 9), date(2026, 1, 10)),
        ]

    def test_a_one_day_range(self) -> None:
        assert windows(date(2026, 1, 1), date(2026, 1, 1), 90) == [(date(2026, 1, 1), date(2026, 1, 1))]

    def test_an_empty_range(self) -> None:
        assert windows(date(2026, 1, 2), date(2026, 1, 1), 90) == []

    def test_rejects_an_empty_window_size(self) -> None:
        with pytest.raises(ValueError, match="at least one day"):
            windows(date(2026, 1, 1), date(2026, 1, 2), 0)


class TestToReading:
    def test_day_is_the_date_of_the_record(self) -> None:
        reading = to_reading(
            VeoliaConsumptionRecord.model_validate(record("2026-07-31", "100.5", "0.26")), Decimal("4.9171")
        )

        assert reading.day == date(2026, 7, 31)
        assert reading.time == datetime(2026, 7, 31, 21, 0)
        assert reading.volume_m3 == Decimal("0.26")
        assert reading.index_m3 == Decimal("100.5")

    def test_liters_and_cost_are_derived(self) -> None:
        reading = to_reading(
            VeoliaConsumptionRecord.model_validate(record("2026-07-31", "100.5", "0.26")), Decimal("4.9171")
        )

        assert reading.liters == 260
        assert reading.index_liters == 100500
        assert reading.cost_eur is not None
        assert round(reading.cost_eur, 2) == Decimal("1.28")  # the figure that the site shows for that day

    def test_no_cost_without_a_price(self) -> None:
        assert to_reading(VeoliaConsumptionRecord.model_validate(record("2026-07-31", "1", "1")), None).cost_eur is None


class TestParseIndexReading:
    def test_parses_index_and_time(self) -> None:
        parsed = parse_index_reading("62.642;2026-07-12 21:00:00")

        assert parsed.index_m3 == Decimal("62.642")
        assert parsed.time == datetime(2026, 7, 12, 21, 0)

    @pytest.mark.parametrize("text", ["62.642", "x;2026-07-12 21:00:00", "62.642;yesterday", ""])
    def test_rejects_malformed_items(self, text: str) -> None:
        with pytest.raises(UnexpectedResponseError):
            parse_index_reading(text)


class TestFlagMeterChanges:
    def make(self, *indexes: str) -> list[Reading]:
        return [
            to_reading(VeoliaConsumptionRecord.model_validate(record(f"2026-01-{day:02d}", index, "1")), None)
            for day, index in enumerate(indexes, start=1)
        ]

    def test_flags_a_drop_of_the_index(self) -> None:
        flagged = flag_meter_changes(self.make("1917", "0", "5", "9"))

        assert [reading.meter_changed for reading in flagged] == [False, True, False, False]

    def test_the_first_reading_is_never_flagged(self) -> None:
        assert flag_meter_changes(self.make("5"))[0].meter_changed is False

    def test_a_flat_index_is_not_a_change(self) -> None:
        assert not any(reading.meter_changed for reading in flag_meter_changes(self.make("5", "5", "6")))

    def test_no_readings(self) -> None:
        assert flag_meter_changes([]) == []


class TestToContract:
    def test_converts_everything(self) -> None:
        contract = to_contract(VeoliaContractDetails.model_validate(contract_details("C-1", ("X1", "X2"))))

        assert (contract.id, contract.number, contract.status, contract.authority) == (
            "C-1",
            "1234567",
            "Actif",
            "SEDIF",
        )
        assert contract.end_date == date(2024, 1, 1)
        assert (contract.site.street, contract.site.postal_code, contract.site.city) == (
            "1 rue Fictive",
            "75001",
            "Paris",
        )
        assert [meter.number for meter in contract.meters] == ["X1", "X2"]
        assert contract.meters[1].meter_token == "meter-token-X2"
        assert (contract.segment, contract.balance, contract.is_individual) == ("PARTICULIER", Decimal("12.5"), True)
        assert contract.customer is not None
        assert contract.customer.email == "jane@example.invalid"
        assert contract.payer is not None
        assert contract.payer.first_name == "Payer"

    def test_personal_data_and_tokens_are_left_out_of_the_repr(self) -> None:
        text = repr(to_contract(VeoliaContractDetails.model_validate(contract_details())))

        for secret in (
            "Jane",
            "Doe",
            "jane@example.invalid",
            "0600000000",
            "1 rue Fictive",
            "75001",
            "meter-token-X1",
            "CC-1",
        ):
            assert secret not in text

    def test_party_may_be_missing(self) -> None:
        assert to_party(None) is None


class TestBuildHistory:
    def test_sorts_and_dedupes_the_windows(self) -> None:
        first = response([record("2026-01-02", "2", "1"), record("2026-01-01", "1", "1")])
        second = response([record("2026-01-02", "2", "1"), record("2026-01-03", "3", "1")])

        history = build_history("C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 3), [first, second], NOW)

        assert [reading.day.day for reading in history.readings] == [1, 2, 3]
        assert [item.index_m3 for item in history.meter_readings] == [1, 2, 3]

    def test_a_daily_history_keeps_only_the_days_of_the_range(self) -> None:
        # The site answers with the day that precedes the start.
        answer = response(
            [record("2025-12-31", "0", "1"), record("2026-01-01", "1", "1"), record("2026-01-02", "2", "1")]
        )

        history = build_history("C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 1), [answer], NOW)

        assert [reading.day for reading in history.readings] == [date(2026, 1, 1)]
        assert [item.time.date() for item in history.meter_readings] == [date(2026, 1, 1)]

    def test_a_weekly_history_is_not_clipped(self) -> None:
        answer = response([record("2025-12-28", "0", "7"), record("2026-01-04", "7", "7")])

        history = build_history("C", METER, Step.WEEK, date(2026, 1, 1), date(2026, 1, 5), [answer], NOW)

        assert len(history.readings) == 2

    def test_flags_the_meter_changes_across_the_windows(self) -> None:
        first = response([record("2026-01-01", "100", "1")])
        second = response([record("2026-01-02", "3", "1")])

        history = build_history("C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 2), [first, second], NOW)

        assert [reading.meter_changed for reading in history.readings] == [False, True]

    def test_takes_the_price_and_the_flags_of_the_site(self) -> None:
        answer = response(
            [record("2026-01-01", "1", "2")],
            prixMoyenEau=5,
            seuilDebitPermanet=1.5,
            showDebitPermanent=True,
            canCompareMonth=False,
        )

        history = build_history("C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 1), [answer], NOW)

        assert history.average_price_eur_m3 == 5
        assert history.readings[0].cost_eur == 10
        assert history.permanent_flow_threshold == Decimal("1.5")
        assert history.shows_permanent_flow is True
        assert history.can_compare_month is False
        assert history.retrieved_at == NOW

    def test_the_period_covers_every_window(self) -> None:
        first = response([], DATE_DEBUT=None)
        first.data.period_start, first.data.period_end = datetime(2026, 1, 1), datetime(2026, 1, 3)
        second = response([])
        second.data.period_start, second.data.period_end = datetime(2026, 1, 4), datetime(2026, 1, 6)

        history = build_history("C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 6), [first, second], NOW)

        assert (history.period_start, history.period_end) == (datetime(2026, 1, 1), datetime(2026, 1, 6))

    def test_takes_the_meter_from_the_answer_or_from_the_meter(self) -> None:
        answer = response([])
        answer.data.meter_number = None
        answer.data.point_id = None

        history = build_history("C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 1), [answer], NOW)

        assert (history.meter_number, history.point_id) == ("X1", "123")

    def test_no_answer(self) -> None:
        history = build_history("C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 1), [], NOW)

        assert history.readings == []
        assert history.period_start is None
        assert history.average_price_eur_m3 is None
        assert history.shows_permanent_flow is False

    def test_a_malformed_index_reading_is_an_unexpected_response(self) -> None:
        with pytest.raises(UnexpectedResponseError):
            build_history(
                "C", METER, Step.DAY, date(2026, 1, 1), date(2026, 1, 1), [response([], indexMesure=["junk"])], NOW
            )
