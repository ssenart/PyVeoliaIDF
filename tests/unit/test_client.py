from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from pyveoliaidf import Client, ClientConfig, ConsumptionHistory, Step, UnknownContractError, UnknownMeterError
from pyveoliaidf.errors import ServerError
from tests.unit.fakes import FakeApi, daily_records
from tests.unit.helpers import record

TODAY = date.today()


def client_for(api: FakeApi, **kwargs: Any) -> Client:
    return Client("user@example.invalid", "password", api=api, **kwargs)


def api_with_days(count: int, **kwargs: Any) -> FakeApi:
    """An API that has a daily record for each of the last count days, up to yesterday."""

    return FakeApi(records=daily_records(TODAY - timedelta(days=count), count), **kwargs)


class TestHistory:
    async def test_converts_the_records_to_readings_oldest_first(self) -> None:
        api = FakeApi(
            records=[
                record("2026-10-06", "144.242", "0.374"),
                record("2026-10-05", "143.868", "0.530", estimated=True),
                record("2026-10-07", "144.590", "0.348"),
            ]
        )

        history = await client_for(api).history(start=date(2026, 10, 5), end=date(2026, 10, 7))

        assert isinstance(history, ConsumptionHistory)
        assert [reading.day.day for reading in history.readings] == [5, 6, 7]
        first = history.readings[0]
        assert first.index_m3 == Decimal("143.868")
        assert first.volume_m3 == Decimal("0.530")
        assert first.liters == 530
        assert first.estimated is True
        assert history.readings[1].estimated is False
        assert history.step == Step.DAY
        assert (history.contract_number, history.meter_number) == ("1234567", "X1")

    async def test_keeps_only_the_days_of_the_range(self) -> None:
        # The fake site, like the real one, answers with the day that precedes the start.
        api = api_with_days(10)

        history = await client_for(api).history(start=TODAY - timedelta(days=5), end=TODAY)

        assert [reading.day for reading in history.readings][0] == TODAY - timedelta(days=5)

    async def test_the_range_ends_today_by_default(self) -> None:
        api = api_with_days(40)

        history = await client_for(api).history(last_n_days=30)

        assert (history.start, history.end) == (TODAY - timedelta(days=30), TODAY)

    async def test_start_wins_over_last_n_days(self) -> None:
        history = await client_for(api_with_days(40)).history(start=TODAY - timedelta(days=3), last_n_days=30)

        assert history.start == TODAY - timedelta(days=3)

    async def test_start_after_end(self) -> None:
        with pytest.raises(ValueError, match="after its end"):
            await client_for(FakeApi()).history(start=date(2026, 2, 1), end=date(2026, 1, 1))

    async def test_no_records(self) -> None:
        history = await client_for(FakeApi()).history(last_n_days=30)

        assert history.readings == []

    async def test_retrieval_time(self) -> None:
        history = await client_for(FakeApi()).history(last_n_days=1)

        assert abs(datetime.now() - history.retrieved_at) < timedelta(seconds=5)


class TestWindowing:
    async def test_the_default_year_is_read_in_windows_that_the_site_accepts(self) -> None:
        api = api_with_days(365)

        history = await client_for(api).history()

        assert len(api.consumption_calls) == 5  # 366 days in windows of 90 days at most
        assert all((last - first).days + 1 <= 90 for _, _, _, first, last in api.consumption_calls)
        days = [reading.day for reading in history.readings]
        assert days == sorted(set(days))
        assert len(days) == 365

    async def test_the_windows_cover_the_range_without_gap_or_overlap(self) -> None:
        api = api_with_days(200)

        await client_for(api).history(start=TODAY - timedelta(days=199), end=TODAY)

        calls = api.consumption_calls
        assert calls[0][3] == TODAY - timedelta(days=199)
        assert calls[-1][4] == TODAY
        for (_, _, _, _, previous_end), (_, _, _, next_start, _) in zip(calls, calls[1:], strict=False):
            assert next_start == previous_end + timedelta(days=1)

    async def test_the_window_size_is_a_setting(self) -> None:
        api = api_with_days(30)

        await client_for(api, config=ClientConfig(max_window_days=10)).history(
            start=TODAY - timedelta(days=29), end=TODAY
        )

        assert len(api.consumption_calls) == 3

    async def test_a_window_that_the_site_refuses_is_an_error(self) -> None:
        with pytest.raises(ServerError, match="de-reference"):
            await client_for(api_with_days(150), config=ClientConfig(max_window_days=150)).history(last_n_days=149)

    async def test_weekly_and_monthly_histories_are_read_in_one_call(self) -> None:
        api = FakeApi(week_records=[record("2026-10-04", "10", "5")], month_records=[record("2026-09-30", "9", "20")])

        weeks = await client_for(api).history(step=Step.WEEK, last_n_days=700)
        months = await client_for(api).history(step=Step.MONTH, last_n_days=700)

        assert [call[2] for call in api.consumption_calls] == [Step.WEEK, Step.MONTH]
        assert weeks.readings[0].volume_m3 == 5
        assert months.readings[0].volume_m3 == 20


class TestMeterChanges:
    async def test_a_drop_of_the_index_is_flagged(self) -> None:
        api = FakeApi(
            records=[
                record((TODAY - timedelta(days=2)).isoformat(), "1917", "1"),
                record((TODAY - timedelta(days=1)).isoformat(), "3", "1"),
            ]
        )

        history = await client_for(api).history(last_n_days=5)

        assert [reading.meter_changed for reading in history.readings] == [False, True]


class TestCostAndSummary:
    async def test_cost_comes_from_the_average_price(self) -> None:
        api = FakeApi(records=[record((TODAY - timedelta(days=1)).isoformat(), "10", "2")], prixMoyenEau=5)

        history = await client_for(api).history(last_n_days=3)

        assert history.readings[0].cost_eur == 10
        assert history.total_cost_eur == 10


class TestContracts:
    async def test_lists_the_contracts_with_their_meters(self) -> None:
        api = FakeApi(contracts={"A": ("X1",), "B": ("X2", "X3")})

        contracts = await client_for(api).contracts()

        assert [contract.number for contract in contracts] == ["A", "B"]
        assert [meter.number for meter in contracts[1].meters] == ["X2", "X3"]
        assert api.logins == 1

    async def test_takes_the_first_contract_and_meter_by_default(self) -> None:
        api = api_with_days(5, contracts={"A": ("X1", "X2"), "B": ("X3",)})

        await client_for(api).history(last_n_days=3)

        assert api.consumption_calls[0][:2] == ("A", "X1")

    async def test_takes_the_contract_and_meter_of_the_client(self) -> None:
        api = api_with_days(5, contracts={"A": ("X1",), "B": ("X3", "X4")})

        history = await client_for(api, contract_number="B", meter_number="X4").history(last_n_days=3)

        assert api.consumption_calls[0][:2] == ("B", "X4")
        assert history.contract_number == "B"

    async def test_a_call_can_override_the_client(self) -> None:
        api = api_with_days(5, contracts={"A": ("X1",), "B": ("X3",)})

        await client_for(api, contract_number="A").history(last_n_days=3, contract_number="B", meter_number="X3")

        assert api.consumption_calls[0][:2] == ("B", "X3")

    async def test_a_contract_is_found_by_its_number_although_the_site_changes_its_identifiers(self) -> None:
        # The identifiers and the tokens of the site are new at each call: only the numbers are stable.
        api = api_with_days(5, contracts={"A": ("X1",), "B": ("X3",)})
        client = client_for(api)

        first = await client.contracts()
        second = await client.contracts()
        history = await client.history(last_n_days=3, contract_number=second[1].number)

        assert first[1].id != second[1].id
        assert first[1].meters[0].meter_token != second[1].meters[0].meter_token
        assert first[1].number == second[1].number == "B"
        assert history.contract_number == "B"

    async def test_the_identifier_of_a_contract_is_not_a_way_to_select_it(self) -> None:
        api = api_with_days(5, contracts={"A": ("X1",)})
        client = client_for(api)
        contract = (await client.contracts())[0]

        with pytest.raises(UnknownContractError):
            await client.history(last_n_days=3, contract_number=contract.id)

    async def test_unknown_contract(self) -> None:
        with pytest.raises(UnknownContractError, match="Z") as error:
            await client_for(api_with_days(5), contract_number="Z").history(last_n_days=3)

        assert error.value.contract_number == "Z"

    async def test_unknown_meter(self) -> None:
        with pytest.raises(UnknownMeterError, match="Z9"):
            await client_for(api_with_days(5)).history(last_n_days=3, meter_number="Z9")

    async def test_account_without_contract(self) -> None:
        with pytest.raises(UnknownContractError):
            await client_for(FakeApi(contracts={})).history(last_n_days=3)

    async def test_logs_in_on_the_first_call_only(self) -> None:
        api = api_with_days(5)
        client = client_for(api)

        await client.history(last_n_days=3)
        await client.history(last_n_days=3)

        assert api.logins == 1


class TestLifecycle:
    async def test_context_manager_logs_in_and_closes(self) -> None:
        api = FakeApi()

        async with client_for(api):
            assert api.logged_in

        assert api.closed

    async def test_context_manager_closes_on_error(self) -> None:
        api = FakeApi()

        with pytest.raises(RuntimeError):
            async with client_for(api):
                raise RuntimeError("boom")

        assert api.closed

    async def test_logout(self) -> None:
        api = FakeApi()
        client = client_for(api)
        await client.login()

        await client.logout()

        assert not api.logged_in

    def test_builds_its_own_api_without_network(self) -> None:
        assert Client("u", "p") is not None
