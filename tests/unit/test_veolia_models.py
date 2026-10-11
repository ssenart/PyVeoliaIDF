from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from pyveoliaidf.veolia_models import VeoliaConsumptionRecord, VeoliaConsumptionResponse, VeoliaContractDetails
from tests.unit.helpers import consumption, contract_details, record


class TestContractDetails:
    def test_keeps_the_identity_and_the_meters(self) -> None:
        details = VeoliaContractDetails.model_validate(contract_details("C-1"))

        assert details.contract.id == "C-1"
        assert details.meters[0].meter_token == "meter-token"
        assert details.meters[0].point_token == "point-token"
        assert details.meters[0].meter_number == "X1"

    def test_drops_the_personal_data(self) -> None:
        details = VeoliaContractDetails.model_validate(contract_details())
        dumped = details.model_dump_json()

        assert "Jane" not in dumped
        assert "jane@example.invalid" not in dumped
        assert "0600000000" not in dumped

    def test_tokens_are_left_out_of_the_repr(self) -> None:
        details = VeoliaContractDetails.model_validate(contract_details())

        assert "meter-token" not in repr(details)
        assert "point-token" not in repr(details)

    def test_needs_a_meter(self) -> None:
        with pytest.raises(ValidationError):
            VeoliaContractDetails.model_validate({**contract_details(), "compteInfo": []})

    def test_needs_a_contract(self) -> None:
        data = contract_details()
        del data["contrat"]

        with pytest.raises(ValidationError):
            VeoliaContractDetails.model_validate(data)


class TestConsumptionRecord:
    def test_reads_the_text_values(self) -> None:
        parsed = VeoliaConsumptionRecord.model_validate(record("2026-10-05", "143.868", "0.53"))

        assert parsed.consumption_m3 == Decimal("0.53")
        assert parsed.index_m3 == Decimal("143.868")
        assert parsed.date_index.isoformat() == "2026-10-05T21:00:00"
        assert parsed.estimated is False

    def test_keeps_unknown_fields(self) -> None:
        parsed = VeoliaConsumptionRecord.model_validate({**record("2026-10-05", "1", "1"), "NEW_FIELD": "x"})

        assert parsed.model_extra == {"DEBIT_PERMANENT": "0", "FLAG_ESTIMATION_INDEX": True, "NEW_FIELD": "x"}

    def test_estimated_flag(self) -> None:
        assert VeoliaConsumptionRecord.model_validate(record("2026-10-05", "1", "1", estimated=True)).estimated is True

    def test_missing_estimated_flag_means_measured(self) -> None:
        data = record("2026-10-05", "1", "1")
        del data["FLAG_ESTIMATION"]

        assert VeoliaConsumptionRecord.model_validate(data).estimated is False

    def test_zero_consumption_is_valid(self) -> None:
        assert VeoliaConsumptionRecord.model_validate(record("2026-10-05", "1", "0")).consumption_m3 == 0

    @pytest.mark.parametrize(
        "changes",
        [
            {"CONSOMMATION": "-0.1"},
            {"CONSOMMATION": "lots"},
            {"VALEUR_INDEX": None},
            {"DATE_INDEX": "yesterday"},
            {"DATE_INDEX": None},
        ],
    )
    def test_rejects_malformed_records(self, changes: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            VeoliaConsumptionRecord.model_validate({**record("2026-10-05", "1", "1"), **changes})


class TestConsumptionResponse:
    def test_reads_the_records_and_the_price(self) -> None:
        response = VeoliaConsumptionResponse.model_validate(
            consumption([record("2026-10-05", "1", "0.1"), record("2026-10-06", "1.1", "0.1")])
        )

        assert len(response.data.records) == 2
        assert response.average_water_price == Decimal("4.9171")

    def test_price_is_optional(self) -> None:
        data = consumption([])
        del data["prixMoyenEau"]

        assert VeoliaConsumptionResponse.model_validate(data).average_water_price is None

    def test_no_records(self) -> None:
        assert VeoliaConsumptionResponse.model_validate(consumption([])).data.records == []

    def test_needs_the_data(self) -> None:
        with pytest.raises(ValidationError):
            VeoliaConsumptionResponse.model_validate({"prixMoyenEau": 1})
