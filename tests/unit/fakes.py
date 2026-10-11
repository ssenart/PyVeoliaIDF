"""Fakes of the lower layers, for the tests of the upper ones."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pyveoliaidf.errors import ServerError
from pyveoliaidf.model import Step
from pyveoliaidf.veolia_models import VeoliaConsumptionResponse, VeoliaContractDetails, VeoliaMeter
from tests.unit.helpers import consumption, contract_details, record

MAX_DAILY_DAYS = 100


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


def daily_records(
    first_day: date, count: int, first_index: Decimal = Decimal(100), per_day: Decimal = Decimal("0.5")
) -> list[dict[str, Any]]:
    """Daily records for count days, with an index that grows by per_day each day."""

    return [
        record(
            (first_day + timedelta(days=offset)).isoformat(),
            str(first_index + per_day * offset),
            str(per_day),
        )
        for offset in range(count)
    ]


class FakeApi:
    """A fake VeoliaApi that behaves like the real site.

    The account has the given contracts, as a dict from the contract number to its meter numbers. Like the real site, it
    makes the identifiers of the contracts and the tokens of the meters anew at each call, so that only the numbers are
    stable. The daily records are the same for every contract. It answers a daily range with the day that precedes the
    start too, and it fails on a daily range of more than about 100 days. The weekly and the monthly records are given
    as they are.
    """

    def __init__(
        self,
        contracts: dict[str, tuple[str, ...]] | None = None,
        records: list[dict[str, Any]] | None = None,
        week_records: list[dict[str, Any]] | None = None,
        month_records: list[dict[str, Any]] | None = None,
        **top: Any,
    ):
        self.contracts = {"1234567": ("X1",)} if contracts is None else contracts
        self.records = records or []
        self.week_records = week_records or []
        self.month_records = month_records or []
        self.top = top
        self.logged_in = False
        self.closed = False
        self.logins = 0
        self.calls = 0
        self.consumption_calls: list[tuple[str, str | None, Step, date, date]] = []

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
        self.calls += 1

        return [f"{number}~list{self.calls}" for number in self.contracts]

    async def get_contract_details(self, contract_id: str) -> VeoliaContractDetails:
        self.calls += 1
        number = contract_id.split("~")[0]

        return VeoliaContractDetails.model_validate(
            contract_details(f"{number}~details{self.calls}", self.contracts[number], number, salt=str(self.calls))
        )

    async def get_consumption(
        self, contract_id: str, meter: VeoliaMeter, step: Step, start_date: date, end_date: date
    ) -> VeoliaConsumptionResponse:
        self.consumption_calls.append((contract_id.split("~")[0], meter.meter_number, step, start_date, end_date))

        if step == Step.DAY:
            if (end_date - start_date).days + 1 > MAX_DAILY_DAYS:
                raise ServerError("The call getData failed: Attempt to de-reference a null object")
            first = start_date - timedelta(days=1)
            records = [
                item for item in self.records if first <= date.fromisoformat(item["DATE_INDEX"][:10]) <= end_date
            ]
        elif step == Step.WEEK:
            records = self.week_records
        else:
            records = self.month_records

        return VeoliaConsumptionResponse.model_validate(consumption(records, **self.top))
