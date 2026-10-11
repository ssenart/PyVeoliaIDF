import warnings
from datetime import date, timedelta
from typing import Any

import pytest

from pyveoliaidf import Client, DailyReading, PropertyNameEnum, UnknownContractError
from tests.unit.fakes import FakeApi
from tests.unit.helpers import record

RECORDS = [
    record("2026-10-06", "144.242", "0.374"),
    record("2026-10-05", "143.868", "0.530", estimated=True),
    record("2026-10-07", "144.590", "0.348"),
]


def client_for(api: FakeApi, **kwargs: Any) -> Client:
    return Client("user@example.invalid", "password", api=api, **kwargs)


class TestLoadSince:
    async def test_converts_the_records_to_readings_oldest_first(self) -> None:
        api = FakeApi(records=RECORDS)

        readings = await client_for(api).load_since(7)

        assert [reading.time.day for reading in readings] == [5, 6, 7]
        first = readings[0]
        assert isinstance(first, DailyReading)
        assert first.total_liter == 143868
        assert first.daily_liter == 530
        assert first.type == "Estimé"
        assert readings[1].type == "Mesuré"
        assert first.timestamp == readings[1].timestamp

    async def test_asks_for_the_window_that_ends_today(self) -> None:
        api = FakeApi(records=RECORDS)

        await client_for(api).load_since(30)

        _, _, start_date, end_date = api.consumption_calls[0]
        assert end_date == date.today()
        assert start_date == date.today() - timedelta(days=30)

    async def test_uses_the_meter_of_the_contract(self) -> None:
        api = FakeApi(records=RECORDS)

        await client_for(api).load_since(30)

        contract_id, meter, _, _ = api.consumption_calls[0]
        assert contract_id == "CONTRACT-1"
        assert meter.meter_token == "meter-token"

    async def test_no_records(self) -> None:
        assert await client_for(FakeApi()).load_since(30) == []

    @pytest.mark.parametrize(
        ("cubic_meters", "liters"), [("0.5304", 530), ("0.5305", 531), ("0", 0), ("12", 12000), ("0.0004", 0)]
    )
    async def test_rounds_volumes_to_the_liter(self, cubic_meters: str, liters: int) -> None:
        api = FakeApi(records=[record("2026-10-05", "100", cubic_meters)])

        readings = await client_for(api).load_since(1)

        assert readings[0].daily_liter == liters


class TestLoadDateRange:
    async def test_passes_the_dates(self) -> None:
        api = FakeApi(records=RECORDS)

        await client_for(api).load_date_range(date(2026, 1, 1), date(2026, 2, 1))

        assert api.consumption_calls[0][2:] == (date(2026, 1, 1), date(2026, 2, 1))


class TestContracts:
    async def test_logs_in_on_the_first_call_only(self) -> None:
        api = FakeApi(records=RECORDS)
        client = client_for(api)

        await client.load_since(7)
        await client.load_since(7)

        assert api.logins == 1

    async def test_takes_the_first_contract_by_default(self) -> None:
        api = FakeApi(contract_ids=["A", "B"], records=RECORDS)

        await client_for(api).load_since(7)

        assert api.consumption_calls[0][0] == "A"

    async def test_takes_the_given_contract(self) -> None:
        api = FakeApi(contract_ids=["A", "B"], records=RECORDS)

        await client_for(api, contract_id="B").load_since(7)

        assert api.consumption_calls[0][0] == "B"

    async def test_unknown_contract(self) -> None:
        api = FakeApi(contract_ids=["A"], records=RECORDS)

        with pytest.raises(UnknownContractError, match="Z"):
            await client_for(api, contract_id="Z").load_since(7)

    async def test_account_without_contract(self) -> None:
        with pytest.raises(UnknownContractError):
            await client_for(FakeApi(contract_ids=[])).load_since(7)

    async def test_lists_the_contract_identifiers(self) -> None:
        api = FakeApi(contract_ids=["A", "B"])

        assert await client_for(api).get_contract_ids() == ["A", "B"]
        assert api.logins == 1


class TestUpdate:
    async def test_keeps_the_readings_as_dicts_with_the_keys_of_the_integration(self) -> None:
        client = client_for(FakeApi(records=RECORDS), last_n_days=7)

        await client.update()

        data = client.data()
        assert len(data) == 3
        assert set(data[0]) == {member.value for member in PropertyNameEnum}
        assert data[0][PropertyNameEnum.TIME.value] == "2026-10-05 21:00:00"
        assert data[0][PropertyNameEnum.TOTAL_LITER.value] == 143868
        assert data[0][PropertyNameEnum.DAILY_LITER.value] == 530
        assert data[0][PropertyNameEnum.TYPE.value] == "Estimé"

    async def test_data_is_replaced_not_appended(self) -> None:
        client = client_for(FakeApi(records=RECORDS), last_n_days=7)

        await client.update()
        await client.update()

        assert len(client.data()) == 3

    async def test_no_records_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        client = client_for(FakeApi())

        await client.update()

        assert client.data() == []
        assert "No records" in caplog.text


class TestLifecycle:
    async def test_context_manager_logs_in_and_closes(self) -> None:
        api = FakeApi(records=RECORDS)

        async with client_for(api):
            assert api.logged_in

        assert api.closed

    async def test_context_manager_closes_on_error(self) -> None:
        api = FakeApi(records=RECORDS)

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


class TestLegacyArguments:
    def test_old_positional_arguments_are_accepted_with_a_warning(self) -> None:
        with pytest.warns(DeprecationWarning, match="browser"):
            Client("u", "p", 5, None, "/usr/bin/firefox", 30, "/tmp", api=FakeApi())

    def test_no_warning_without_them(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            Client("u", "p", 5, api=FakeApi())

    def test_builds_its_own_api_without_network(self) -> None:
        assert Client("u", "p") is not None
