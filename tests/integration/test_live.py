"""Live tests against the Veolia site. They only read, and run with: pytest -m integration"""

import asyncio
import json
import sys
from datetime import date, timedelta
from decimal import Decimal

import pytest

from pyveoliaidf import (
    AuraClient,
    Client,
    LoginError,
    NotLoggedInError,
    ServerError,
    Step,
    UnknownContractError,
    UnknownMeterError,
    VeoliaApiClient,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

TODAY = date.today()
LAST_N_DAYS = 30


# ------------------------------------------------------------------------------------------------------------
# Contracts
async def test_lists_the_contracts_with_their_meters(client: Client) -> None:
    contracts = await client.contracts()

    assert contracts
    for contract in contracts:
        assert contract.id
        assert contract.meters
        assert all(meter.meter_token and meter.point_token for meter in contract.meters)
        assert contract.status


async def test_personal_data_stays_out_of_the_repr(client: Client) -> None:
    contract = (await client.contracts())[0]
    text = repr(contract)

    for party in (contract.customer, contract.payer):
        if party is not None:
            for secret in (party.email, party.mobile_phone, party.last_name):
                assert not secret or secret not in text
    assert not contract.meters[0].meter_token or contract.meters[0].meter_token not in text


async def test_a_contract_and_a_meter_are_selected_by_their_numbers(client: Client) -> None:
    contract = (await client.contracts())[0]
    meter = contract.meters[0]

    history = await client.history(last_n_days=7, contract_number=contract.number, meter_number=meter.number)

    assert history.readings
    assert (history.contract_number, history.meter_number) == (contract.number, meter.number)


async def test_the_identifiers_of_the_site_change_at_each_call_but_the_numbers_do_not(client: Client) -> None:
    first = (await client.contracts())[0]
    second = (await client.contracts())[0]

    assert first.number == second.number
    assert first.meters[0].number == second.meters[0].number
    if first.id == second.id:
        pytest.skip("The site keeps its identifiers stable now: selecting by identifier may be possible.")


async def test_an_unknown_contract_is_refused(client: Client) -> None:
    with pytest.raises(UnknownContractError):
        await client.history(last_n_days=3, contract_number="NOT-A-CONTRACT")


async def test_an_unknown_meter_is_refused(client: Client) -> None:
    with pytest.raises(UnknownMeterError):
        await client.history(last_n_days=3, meter_number="NOT-A-METER")


# ------------------------------------------------------------------------------------------------------------
# Daily history
async def test_the_default_year_is_read_through_windows(client: Client) -> None:
    # The site refuses a daily range of about 100 days or more: the client has to cut it.
    history = await client.history()
    days = [reading.day for reading in history.readings]

    assert days == sorted(set(days))
    assert len(days) >= 300
    assert days[0] >= TODAY - timedelta(days=365)
    assert days[-1] <= TODAY


async def test_daily_readings_are_well_formed(client: Client) -> None:
    history = await client.history(last_n_days=LAST_N_DAYS)

    assert history.readings
    assert all(reading.volume_m3 >= 0 and reading.index_m3 >= 0 for reading in history.readings)
    assert all(reading.time.date() == reading.day for reading in history.readings)
    assert history.average_price_eur_m3 is not None and history.average_price_eur_m3 > 0
    assert all(reading.cost_eur == reading.volume_m3 * history.average_price_eur_m3 for reading in history.readings)


async def test_the_index_only_goes_back_when_the_meter_changes(client: Client) -> None:
    readings = (await client.history()).readings

    for previous, current in zip(readings, readings[1:], strict=False):
        assert current.index_m3 >= previous.index_m3 or current.meter_changed, current.day


async def test_daily_volume_matches_the_index_difference(client: Client) -> None:
    readings = (await client.history(last_n_days=LAST_N_DAYS)).readings

    for previous, current in zip(readings, readings[1:], strict=False):
        # The volume of an estimated day is not reconciled with the index yet, and a meter change breaks the index.
        if not (current.meter_changed or current.estimated or previous.estimated):
            assert abs((current.index_m3 - previous.index_m3) - current.volume_m3) <= Decimal("0.002"), current.day


async def test_the_summary_is_consistent(client: Client) -> None:
    history = await client.history(last_n_days=LAST_N_DAYS)

    assert history.minimum is not None and history.maximum is not None
    assert history.minimum.volume_m3 <= history.average_m3 <= history.maximum.volume_m3  # type: ignore[operator]
    assert history.total_m3 == sum((reading.volume_m3 for reading in history.readings), Decimal(0))
    assert history.meter_readings


async def test_a_short_range_has_fewer_readings(client: Client) -> None:
    week = await client.history(last_n_days=7)
    month = await client.history(last_n_days=30)

    assert 0 < len(week.readings) <= len(month.readings)


# ------------------------------------------------------------------------------------------------------------
# Steps
async def test_a_weekly_reading_covers_the_seven_days_that_end_on_its_day(client: Client) -> None:
    # A weekly reading is dated its Sunday. Its volume is the difference of the index since the previous week, which is
    # the sum of its seven days, except when some of those days are still estimated.
    days = {reading.day: reading for reading in (await client.history(last_n_days=70)).readings}
    weeks = (await client.history(step=Step.WEEK, last_n_days=70)).readings

    by_index = 0
    by_days = 0
    for previous, week in zip(weeks, weeks[1:], strict=False):
        assert week.volume_m3 == week.index_m3 - previous.index_m3, week.day
        by_index += 1

        covered = [days.get(week.day - timedelta(days=offset)) for offset in range(7)]
        if all(day is not None and not day.estimated for day in covered):
            assert sum(day.volume_m3 for day in covered if day) == week.volume_m3, week.day
            by_days += 1

    assert by_index >= 3
    assert by_days >= 3


async def test_monthly_readings(client: Client) -> None:
    history = await client.history(step=Step.MONTH, last_n_days=400)

    assert history.step == Step.MONTH
    assert len(history.readings) >= 10
    assert all(reading.volume_m3 > 0 for reading in history.readings)


# ------------------------------------------------------------------------------------------------------------
# The assumptions about the site
async def test_the_site_still_refuses_a_long_daily_range(credentials: tuple[str, str]) -> None:
    aura = AuraClient(*credentials)
    api = VeoliaApiClient(aura)
    try:
        await api.login()
        contract_id = (await api.list_contract_ids())[0]
        meter = (await api.get_contract_details(contract_id)).meters[0]

        try:
            await api.get_consumption(contract_id, meter, Step.DAY, TODAY - timedelta(days=150), TODAY)
        except ServerError:
            return
        pytest.skip("The site accepts a long daily range now: the windowing may no longer be needed.")
    finally:
        await api.close()


# ------------------------------------------------------------------------------------------------------------
# Sessions and login
async def test_a_new_login_after_logout(credentials: tuple[str, str]) -> None:
    live_client = Client(*credentials)
    try:
        await live_client.login()
        await live_client.logout()
        assert (await live_client.history(last_n_days=3)).readings is not None
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


# ------------------------------------------------------------------------------------------------------------
# Command line
async def run_cli(credentials: tuple[str, str], *arguments: str) -> object:
    username, password = credentials
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pyveoliaidf",
        "-u",
        username,
        "-p",
        password,
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), timeout=180)

    assert process.returncode == 0, output[-500:]

    return json.loads(output)


async def test_cli_history(credentials: tuple[str, str]) -> None:
    result = await run_cli(credentials, "-d", "7")

    assert isinstance(result, dict)
    assert result["readings"]
    assert result["step"] == "day"


async def test_cli_contracts(credentials: tuple[str, str]) -> None:
    result = await run_cli(credentials, "--contracts")

    assert isinstance(result, list)
    assert result[0]["meters"]
