"""The public client of PyVeoliaIDF: the upper layer, which gives contracts and consumption histories as models.

It asks the lower layer (api_client.py) for the raw answers of the site and converts them to the model of model.py.
"""

import logging
from datetime import date, datetime, timedelta
from types import TracebackType

import aiohttp

from pyveoliaidf.api_client import VeoliaApi, VeoliaApiClient
from pyveoliaidf.aura import AuraClient
from pyveoliaidf.config import ClientConfig
from pyveoliaidf.convert import build_history, to_contract, to_meter, windows
from pyveoliaidf.errors import UnknownContractError, UnknownMeterError
from pyveoliaidf.model import ConsumptionHistory, Contract, Step
from pyveoliaidf.veolia_models import VeoliaContractDetails, VeoliaMeter

DEFAULT_LAST_N_DAYS = 365

Logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------------------------------
class Client:
    """Reads the contracts and the water consumption of a Veolia Ile-de-France account.

    The client logs in on its first call and keeps its session. Use it as an async context manager so that the session
    ends whatever happens:

        async with Client(username, password) as client:
            history = await client.history(last_n_days=30)
            for reading in history.readings:
                print(reading.day, reading.volume_m3)

    Without a contract number or a meter number, the first contract and its first meter are read. The aiohttp session that is given must keep
    cookies and trust the certificates of the site (see AuraClient). The client closes the sessions it created itself,
    never the one it was given.
    """

    # ------------------------------------------------------
    def __init__(
        self,
        username: str,
        password: str,
        *,
        contract_number: str | None = None,
        meter_number: str | None = None,
        config: ClientConfig | None = None,
        session: aiohttp.ClientSession | None = None,
        api: VeoliaApi | None = None,
    ):
        self._config = config or ClientConfig()
        self._api: VeoliaApi = api or VeoliaApiClient(AuraClient(username, password, self._config, session))
        self._contract_number = contract_number
        self._meter_number = meter_number

    # ------------------------------------------------------
    async def __aenter__(self) -> "Client":
        await self.login()

        return self

    # ------------------------------------------------------
    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
    ) -> None:
        await self.close()

    # ------------------------------------------------------
    async def login(self) -> None:
        await self._api.login()

    # ------------------------------------------------------
    async def logout(self) -> None:
        await self._api.logout()

    # ------------------------------------------------------
    async def close(self) -> None:
        await self._api.close()

    # ------------------------------------------------------
    async def contracts(self) -> list[Contract]:
        """Returns the active contracts of the account, with their meters."""

        await self._ensure_login()

        return [
            to_contract(await self._api.get_contract_details(contract_id))
            for contract_id in await self._api.list_contract_ids()
        ]

    # ------------------------------------------------------
    async def history(
        self,
        *,
        step: Step = Step.DAY,
        start: date | None = None,
        end: date | None = None,
        last_n_days: int = DEFAULT_LAST_N_DAYS,
        contract_number: str | None = None,
        meter_number: str | None = None,
    ) -> ConsumptionHistory:
        """Returns the readings of a meter between two dates, oldest first.

        The range ends at end (today by default) and starts at start, or last_n_days before the end. The site refuses a
        daily history of more than about 100 days, so a longer one is read in windows (config.max_window_days) and
        merged. A weekly or monthly history is read in one call, and the site rounds its range to whole periods.
        """

        await self._ensure_login()

        end = end or date.today()
        start = start or end - timedelta(days=last_n_days)
        if start > end:
            raise ValueError("The start of the range is after its end.")

        contract_id, details = await self._resolve_contract(contract_number)
        raw_meter = self._resolve_meter(details, meter_number)

        ranges = windows(start, end, self._config.max_window_days) if step == Step.DAY else [(start, end)]
        responses = [
            await self._api.get_consumption(contract_id, raw_meter, step, first, last) for first, last in ranges
        ]

        return build_history(details.contract.number, to_meter(raw_meter), step, start, end, responses, datetime.now())

    # ------------------------------------------------------
    async def _ensure_login(self) -> None:
        if not self._api.is_logged_in():
            await self._api.login()

    # ------------------------------------------------------
    async def _resolve_contract(self, contract_number: str | None) -> tuple[str, VeoliaContractDetails]:
        """Returns the identifier to call the site with, and the details of the contract.

        The site makes the identifiers anew at each call, so a contract is found by its number, which is stable: the
        details of each contract are read until one has it.
        """

        wanted = contract_number or self._contract_number
        contract_ids = await self._api.list_contract_ids()

        if wanted is None:
            if not contract_ids:
                raise UnknownContractError("(none)")

            return contract_ids[0], await self._api.get_contract_details(contract_ids[0])

        for contract_id in contract_ids:
            details = await self._api.get_contract_details(contract_id)
            if details.contract.number == wanted:
                return contract_id, details

        raise UnknownContractError(wanted)

    # ------------------------------------------------------
    def _resolve_meter(self, details: VeoliaContractDetails, meter_number: str | None) -> VeoliaMeter:
        wanted = meter_number or self._meter_number
        if wanted is None:
            return details.meters[0]

        for meter in details.meters:
            if meter.meter_number == wanted:
                return meter

        raise UnknownMeterError(wanted)
