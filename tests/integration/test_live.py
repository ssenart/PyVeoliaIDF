"""Live tests against the Veolia site. They only read, and run with: pytest -m integration"""

import asyncio
import json
import sys
from datetime import date, timedelta

import pytest

from pyveoliaidf import Client, DailyReading, LoginError, NotLoggedInError, PropertyNameEnum
from pyveoliaidf.aura import AuraClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

LAST_N_DAYS = 14


async def test_lists_the_contracts(client: Client) -> None:
    contract_ids = await client.get_contract_ids()

    assert contract_ids
    assert all(isinstance(contract_id, str) and contract_id for contract_id in contract_ids)


async def test_loads_well_formed_daily_readings(client: Client) -> None:
    readings = await client.load_since(LAST_N_DAYS)

    assert readings
    assert all(isinstance(reading, DailyReading) for reading in readings)
    assert [reading.time for reading in readings] == sorted(reading.time for reading in readings)
    assert {reading.type for reading in readings} <= {"Mesuré", "Estimé"}
    assert all(reading.daily_liter >= 0 for reading in readings)
    assert max(reading.time.date() for reading in readings) <= date.today()


async def test_the_meter_index_never_goes_back(client: Client) -> None:
    readings = await client.load_since(LAST_N_DAYS)

    totals = [reading.total_liter for reading in readings]
    assert totals == sorted(totals)


async def test_daily_volume_matches_the_index_difference(client: Client) -> None:
    readings = await client.load_since(LAST_N_DAYS)

    for previous, current in zip(readings, readings[1:], strict=False):
        # The index and the volume are both rounded to the liter, so the sum of two roundings can differ by a liter or two.
        assert abs((current.total_liter - previous.total_liter) - current.daily_liter) <= 2, current.time


async def test_a_short_range_returns_fewer_readings(client: Client) -> None:
    end = date.today()
    week = await client.load_date_range(end - timedelta(days=7), end)
    month = await client.load_date_range(end - timedelta(days=30), end)

    assert 0 < len(week) <= len(month)


async def test_update_fills_the_dict_form(credentials: tuple[str, str]) -> None:
    async with Client(*credentials, LAST_N_DAYS) as live_client:
        await live_client.update()

        data = live_client.data()

    assert data
    assert set(data[0]) == {member.value for member in PropertyNameEnum}
    assert isinstance(data[0][PropertyNameEnum.TOTAL_LITER.value], int)


async def test_a_new_login_after_logout(credentials: tuple[str, str]) -> None:
    live_client = Client(*credentials, LAST_N_DAYS)
    try:
        await live_client.login()
        await live_client.logout()
        assert await live_client.load_since(3) is not None
    finally:
        await live_client.close()


async def test_wrong_password_is_a_login_error(credentials: tuple[str, str]) -> None:
    username, _ = credentials
    aura = AuraClient(username, "definitely-not-the-password")
    try:
        with pytest.raises(LoginError):
            await aura.login()
        with pytest.raises(NotLoggedInError):
            await aura.call_apex("LTN009_ICL_ContratsGroupements", "listCurrentUserActiveContrats")
    finally:
        await aura.close()


async def test_cli_end_to_end(credentials: tuple[str, str]) -> None:
    username, password = credentials

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pyveoliaidf",
        "-u",
        username,
        "-p",
        password,
        "-d",
        "7",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), timeout=120)

    assert process.returncode == 0, output[-500:]
    assert json.loads(output)
