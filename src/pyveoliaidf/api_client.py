"""The Veolia API: the Apex methods of the customer area, with their parameters and their answers validated.

This is the lower layer of the library. It knows the names of the methods and what they take and give, and returns the
raw models of veolia_models.py. The conversion to the model that users get is the work of the upper layer (client.py).
"""

import logging
from datetime import date
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from pyveoliaidf.aura import AuraTransport
from pyveoliaidf.errors import UnexpectedResponseError
from pyveoliaidf.model import Step
from pyveoliaidf.veolia_models import VeoliaConsumptionResponse, VeoliaContractDetails, VeoliaMeter

CONTRACTS_CLASS = "LTN009_ICL_ContratsGroupements"
CONTRACT_DETAILS_CLASS = "LTN008_ICL_ContratDetails"
CONSUMPTION_CLASS = "LTN015_ICL_ContratConsoHisto"

HISTORY_PAGE_URI = "/espace-particuliers/s/historique"

DATE_FORMAT = "%Y-%m-%d"

# The steps, as the consumption method names them.
API_STEPS = {Step.DAY: "JOURNEE", Step.WEEK: "SEMAINE", Step.MONTH: "MOIS"}

ModelT = TypeVar("ModelT", bound=BaseModel)

Logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------------------------------
class VeoliaApi(Protocol):
    """What the upper layer needs from the lower one: the tests give it a fake."""

    async def login(self) -> None: ...

    async def logout(self) -> None: ...

    def is_logged_in(self) -> bool: ...

    async def close(self) -> None: ...

    async def list_contract_ids(self) -> list[str]: ...

    async def get_contract_details(self, contract_id: str) -> VeoliaContractDetails: ...

    async def get_consumption(
        self, contract_id: str, meter: VeoliaMeter, step: Step, start_date: date, end_date: date
    ) -> VeoliaConsumptionResponse: ...


# ------------------------------------------------------------------------------------------------------------
def validate(model: type[ModelT], value: Any, what: str) -> ModelT:
    """Returns the value as a model, or raises an UnexpectedResponseError that names the fields in error.

    The values are left out of the message: they may be personal.
    """

    try:
        return model.model_validate(value)
    except ValidationError as error:
        fields = sorted({".".join(str(part) for part in detail["loc"]) for detail in error.errors()})
        raise UnexpectedResponseError(f"The {what} is not as expected (fields: {', '.join(fields)}).") from error


# ------------------------------------------------------------------------------------------------------------
class VeoliaApiClient:
    # ------------------------------------------------------
    def __init__(self, transport: AuraTransport):
        self._transport = transport

    # ------------------------------------------------------
    async def login(self) -> None:
        await self._transport.login()

    # ------------------------------------------------------
    async def logout(self) -> None:
        await self._transport.logout()

    # ------------------------------------------------------
    def is_logged_in(self) -> bool:
        return self._transport.is_logged_in()

    # ------------------------------------------------------
    async def close(self) -> None:
        await self._transport.close()

    # ------------------------------------------------------
    async def list_contract_ids(self) -> list[str]:
        """Returns the identifiers of the active contracts of the account."""

        value = await self._transport.call_apex(CONTRACTS_CLASS, "listCurrentUserActiveContrats")
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise UnexpectedResponseError("The list of the contracts is not a list of identifiers.")

        return list(value)

    # ------------------------------------------------------
    async def get_contract_details(self, contract_id: str) -> VeoliaContractDetails:

        value = await self._transport.call_apex(CONTRACT_DETAILS_CLASS, "getContratDetails", {"contratId": contract_id})

        return validate(VeoliaContractDetails, value, "contract details")

    # ------------------------------------------------------
    async def get_consumption(
        self, contract_id: str, meter: VeoliaMeter, step: Step, start_date: date, end_date: date
    ) -> VeoliaConsumptionResponse:
        """Returns the consumption of a meter over a range. The site refuses a daily range of more than about 100 days."""

        value = await self._transport.call_apex(
            CONSUMPTION_CLASS,
            "getData",
            {
                "contractId": contract_id,
                "TYPE_PAS": API_STEPS[step],
                "DATE_DEBUT": start_date.strftime(DATE_FORMAT),
                "DATE_FIN": end_date.strftime(DATE_FORMAT),
                "NUMERO_COMPTEUR": meter.meter_token,
                "ID_PDS": meter.point_token,
            },
            page_uri=HISTORY_PAGE_URI,
        )

        return validate(VeoliaConsumptionResponse, value, "consumption history")
