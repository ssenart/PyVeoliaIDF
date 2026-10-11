"""The public client of PyVeoliaIDF: the upper layer, which gives the readings as models.

It asks the lower layer (api_client.py) for the raw answers of the site and converts them to the model of model.py.
"""

import logging
import warnings
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import TracebackType
from typing import Any

import aiohttp

from pyveoliaidf.api_client import VeoliaApi, VeoliaApiClient
from pyveoliaidf.aura import AuraClient
from pyveoliaidf.config import ClientConfig
from pyveoliaidf.errors import LoginError, UnknownContractError  # noqa: F401
from pyveoliaidf.model import ESTIMATED, MEASURED, DailyReading
from pyveoliaidf.veolia_models import VeoliaConsumptionRecord

DEFAULT_LAST_N_DAYS = 365

LITERS_PER_CUBIC_METER = Decimal(1000)

# The arguments that the Selenium-based client took after last_n_days: they have no meaning any more.
LEGACY_ARGUMENTS = ("firefox_webdriver_executable", "firefox_binary_location", "wait_time", "tmp_directory")

Logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------------------------------
def to_liters(cubic_meters: Decimal) -> int:
    """Returns a volume in liters from a volume in cubic meters, rounded to the liter."""

    return int((cubic_meters * LITERS_PER_CUBIC_METER).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ------------------------------------------------------------------------------------------------------------
def to_daily_reading(record: VeoliaConsumptionRecord, timestamp: str) -> DailyReading:
    """Converts a raw consumption record to the reading that users get."""

    return DailyReading(
        time=record.date_index,
        total_liter=to_liters(record.index_m3),
        daily_liter=to_liters(record.consumption_m3),
        type=ESTIMATED if record.estimated else MEASURED,
        timestamp=timestamp,
    )


# ------------------------------------------------------------------------------------------------------------
class Client:
    """Reads the water consumption of a Veolia Ile-de-France account.

    The client logs in on its first call and keeps its session. Use it as an async context manager so that the session
    ends whatever happens:

        async with Client(username, password) as client:
            await client.update()
            print(client.data())

    The aiohttp session that is given must keep cookies and trust the certificates of the site (see AuraClient). The
    client closes the sessions it created itself, never the one it was given.
    """

    # ------------------------------------------------------
    def __init__(
        self,
        username: str,
        password: str,
        last_n_days: int = DEFAULT_LAST_N_DAYS,
        *legacy_arguments: Any,
        contract_id: str | None = None,
        config: ClientConfig | None = None,
        session: aiohttp.ClientSession | None = None,
        api: VeoliaApi | None = None,
    ):
        if legacy_arguments:
            warnings.warn(
                f"The arguments {', '.join(LEGACY_ARGUMENTS)} are ignored: the client does not use a browser any more.",
                DeprecationWarning,
                stacklevel=2,
            )

        self._api: VeoliaApi = api or VeoliaApiClient(AuraClient(username, password, config, session))
        self._last_n_days = last_n_days
        self._contract_id = contract_id
        self._data: list[dict[str, Any]] = []

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
    def data(self) -> list[dict[str, Any]]:
        """Returns the readings of the last update() as dicts, the form the Home Assistant integration reads."""

        return self._data

    # ------------------------------------------------------
    async def get_contract_ids(self) -> list[str]:
        await self._ensure_login()

        return await self._api.list_contract_ids()

    # ------------------------------------------------------
    async def update(self) -> None:
        """Loads the readings of the last N days, and keeps them for data()."""

        readings = await self.load_since(self._last_n_days)
        self._data = [reading.as_dict() for reading in readings]

        if self._data:
            Logger.info(
                "Retrieved %d records from %s to %s", len(self._data), self._data[0]["time"], self._data[-1]["time"]
            )
        else:
            Logger.warning("No records retrieved")

    # ------------------------------------------------------
    async def load_since(self, last_n_days: int = DEFAULT_LAST_N_DAYS) -> list[DailyReading]:
        """Returns the daily readings of the last N days, oldest first."""

        end_date = date.today()

        return await self.load_date_range(end_date - timedelta(days=last_n_days), end_date)

    # ------------------------------------------------------
    async def load_date_range(self, start_date: date, end_date: date) -> list[DailyReading]:
        """Returns the daily readings between two dates, oldest first."""

        await self._ensure_login()

        contract_id = await self._resolve_contract_id()
        details = await self._api.get_contract_details(contract_id)
        response = await self._api.get_daily_consumption(contract_id, details.meters[0], start_date, end_date)

        timestamp = datetime.now().isoformat()
        readings = [to_daily_reading(record, timestamp) for record in response.data.records]

        return sorted(readings, key=lambda reading: reading.time)

    # ------------------------------------------------------
    async def _ensure_login(self) -> None:
        if not self._api.is_logged_in():
            await self._api.login()

    # ------------------------------------------------------
    async def _resolve_contract_id(self) -> str:
        contract_ids = await self._api.list_contract_ids()

        if self._contract_id is not None:
            if self._contract_id not in contract_ids:
                raise UnknownContractError(self._contract_id)

            return self._contract_id

        if not contract_ids:
            raise UnknownContractError("(none)")

        return contract_ids[0]
