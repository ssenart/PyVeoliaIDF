from datetime import date
from typing import Any

import pytest

from pyveoliaidf.api_client import VeoliaApiClient
from pyveoliaidf.errors import ServerError, UnexpectedResponseError
from tests.unit.fakes import FakeTransport
from tests.unit.helpers import consumption, contract_details, record

CONTRACTS = ("LTN009_ICL_ContratsGroupements", "listCurrentUserActiveContrats")
DETAILS = ("LTN008_ICL_ContratDetails", "getContratDetails")
HISTORY = ("LTN015_ICL_ContratConsoHisto", "getData")


class TestSession:
    async def test_login_logout_and_close_go_to_the_transport(self) -> None:
        transport = FakeTransport()
        api = VeoliaApiClient(transport)

        assert not api.is_logged_in()
        await api.login()
        assert api.is_logged_in()
        await api.logout()
        assert not api.is_logged_in()
        await api.close()
        assert transport.closed


class TestListContractIds:
    async def test_returns_the_identifiers(self) -> None:
        api = VeoliaApiClient(FakeTransport({CONTRACTS: ["A", "B"]}))

        assert await api.list_contract_ids() == ["A", "B"]

    async def test_no_contract_is_an_empty_list(self) -> None:
        api = VeoliaApiClient(FakeTransport({CONTRACTS: None}))

        assert await api.list_contract_ids() == []

    @pytest.mark.parametrize("value", ["A", {"A": 1}, [1, 2], ["A", None]])
    async def test_rejects_other_shapes(self, value: Any) -> None:
        api = VeoliaApiClient(FakeTransport({CONTRACTS: value}))

        with pytest.raises(UnexpectedResponseError):
            await api.list_contract_ids()


class TestGetContractDetails:
    async def test_sends_the_contract_and_returns_the_details(self) -> None:
        transport = FakeTransport({DETAILS: contract_details("C-1")})
        api = VeoliaApiClient(transport)

        details = await api.get_contract_details("C-1")

        assert details.contract.id == "C-1"
        assert transport.calls == [(*DETAILS, {"contratId": "C-1"}, "/default")]

    async def test_names_the_fields_in_error_but_not_their_values(self) -> None:
        data = contract_details()
        data["compteInfo"] = []
        data["contratClient"] = {"LastName": "Doe"}
        api = VeoliaApiClient(FakeTransport({DETAILS: data}))

        with pytest.raises(UnexpectedResponseError, match="compteInfo") as error:
            await api.get_contract_details("C-1")

        assert "Doe" not in str(error.value)


class TestGetDailyConsumption:
    async def test_sends_the_meter_tokens_and_the_dates(self) -> None:
        transport = FakeTransport(
            {DETAILS: contract_details(), HISTORY: consumption([record("2026-10-05", "1", "0.5")])}
        )
        api = VeoliaApiClient(transport)
        details = await api.get_contract_details("C-1")

        response = await api.get_daily_consumption("C-1", details.meters[0], date(2026, 10, 1), date(2026, 10, 6))

        assert len(response.data.records) == 1
        classname, method, params, page_uri = transport.calls[-1]
        assert (classname, method) == HISTORY
        assert params == {
            "contractId": "C-1",
            "TYPE_PAS": "JOURNEE",
            "DATE_DEBUT": "2026-10-01",
            "DATE_FIN": "2026-10-06",
            "NUMERO_COMPTEUR": "meter-token",
            "ID_PDS": "point-token",
        }
        assert page_uri == "/espace-particuliers/s/historique"

    async def test_rejects_a_malformed_answer(self) -> None:
        transport = FakeTransport(
            {DETAILS: contract_details(), HISTORY: {"data": {"CONSOMMATION": [{"VALEUR_INDEX": "x"}]}}}
        )
        api = VeoliaApiClient(transport)
        details = await api.get_contract_details("C-1")

        with pytest.raises(UnexpectedResponseError, match="consumption history"):
            await api.get_daily_consumption("C-1", details.meters[0], date(2026, 10, 1), date(2026, 10, 6))

    async def test_transport_errors_pass_through(self) -> None:
        transport = FakeTransport({DETAILS: contract_details(), HISTORY: ServerError("down")})
        api = VeoliaApiClient(transport)
        details = await api.get_contract_details("C-1")

        with pytest.raises(ServerError, match="down"):
            await api.get_daily_consumption("C-1", details.meters[0], date(2026, 10, 1), date(2026, 10, 6))
