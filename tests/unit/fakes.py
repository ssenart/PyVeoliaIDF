"""Fakes of the lower layers, for the tests of the upper ones."""

from datetime import date
from typing import Any

from pyveoliaidf.veolia_models import VeoliaConsumptionResponse, VeoliaContractDetails, VeoliaMeter
from tests.unit.helpers import consumption, contract_details


class FakeTransport:
    """A fake AuraTransport: it answers the Apex calls from a table, and remembers the calls."""

    def __init__(self, answers: dict[tuple[str, str], Any] | None = None):
        self.answers = answers or {}
        self.calls: list[tuple[str, str, dict[str, Any] | None, str]] = []
        self.logged_in = False
        self.closed = False
        self.logins = 0

    async def login(self) -> None:
        self.logged_in = True
        self.logins += 1

    async def logout(self) -> None:
        self.logged_in = False

    def is_logged_in(self) -> bool:
        return self.logged_in

    async def close(self) -> None:
        self.closed = True
        self.logged_in = False

    async def call_apex(
        self, classname: str, method: str, params: dict[str, Any] | None = None, page_uri: str = "/default"
    ) -> Any:
        self.calls.append((classname, method, params, page_uri))
        answer = self.answers[(classname, method)]
        if isinstance(answer, Exception):
            raise answer

        return answer


class FakeApi:
    """A fake VeoliaApi: the account has the given contracts, and each contract has the given consumption records."""

    def __init__(self, contract_ids: list[str] | None = None, records: list[dict[str, Any]] | None = None):
        self.contract_ids = ["CONTRACT-1"] if contract_ids is None else contract_ids
        self.records = records or []
        self.logged_in = False
        self.closed = False
        self.logins = 0
        self.consumption_calls: list[tuple[str, VeoliaMeter, date, date]] = []

    async def login(self) -> None:
        self.logged_in = True
        self.logins += 1

    async def logout(self) -> None:
        self.logged_in = False

    def is_logged_in(self) -> bool:
        return self.logged_in

    async def close(self) -> None:
        self.closed = True
        self.logged_in = False

    async def list_contract_ids(self) -> list[str]:
        return self.contract_ids

    async def get_contract_details(self, contract_id: str) -> VeoliaContractDetails:
        return VeoliaContractDetails.model_validate(contract_details(contract_id))

    async def get_daily_consumption(
        self, contract_id: str, meter: VeoliaMeter, start_date: date, end_date: date
    ) -> VeoliaConsumptionResponse:
        self.consumption_calls.append((contract_id, meter, start_date, end_date))

        return VeoliaConsumptionResponse.model_validate(consumption(self.records))
