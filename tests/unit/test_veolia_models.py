from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from pyveoliaidf.veolia_models import (
    VeoliaConsumptionData,
    VeoliaConsumptionRecord,
    VeoliaConsumptionResponse,
    VeoliaContractDetails,
)
from tests.unit.helpers import consumption, contract_details, record


class TestContractDetails:
    def test_reads_everything_the_site_sends(self) -> None:
        details = VeoliaContractDetails.model_validate(contract_details("C-1"))

        assert details.contract.id == "C-1"
        assert details.contract.number == "1234567"
        assert details.contract.status == "Actif"
        assert details.contract.authority == "SEDIF"
        assert details.contract.end_date is not None
        assert details.contract.end_date.isoformat() == "2024-01-01"
        assert (details.contract.street, details.contract.postal_code, details.contract.city) == (
            "1 rue Fictive",
            "75001",
            "Paris",
        )
        assert details.segment == "PARTICULIER"
        assert details.balance == Decimal("12.5")
        assert details.is_individual is True
        assert details.has_multiple_contracts is False
        assert details.meters[0].meter_token == "meter-token-X1"
        assert details.meters[0].point_token == "point-token-X1"
        assert details.meters[0].point_id == "1234567890"
        assert details.meters[0].meter_number == "X1"

    def test_reads_the_customer_and_the_payer(self) -> None:
        details = VeoliaContractDetails.model_validate(contract_details())

        assert details.customer is not None
        assert details.payer is not None
        assert (details.customer.first_name, details.payer.first_name) == ("Jane", "Payer")
        assert details.customer.email == "jane@example.invalid"
        assert details.customer.mobile_phone == "0600000000"
        assert details.customer.billing_city == "Paris"
        assert details.customer.locked is False

    def test_the_customer_and_the_payer_are_optional(self) -> None:
        data = contract_details()
        del data["contratClient"]
        del data["payeurClient"]

        details = VeoliaContractDetails.model_validate(data)

        assert details.customer is None
        assert details.payer is None

    def test_personal_data_and_tokens_are_left_out_of_the_repr(self) -> None:
        text = repr(VeoliaContractDetails.model_validate(contract_details()))

        for secret in (
            "Jane",
            "Doe",
            "jane@example.invalid",
            "0600000000",
            "1 rue Fictive",
            "meter-token-X1",
            "point-token-X1",
        ):
            assert secret not in text

    def test_needs_a_meter(self) -> None:
        with pytest.raises(ValidationError):
            VeoliaContractDetails.model_validate({**contract_details(), "compteInfo": []})

    def test_needs_a_contract(self) -> None:
        data = contract_details()
        del data["contrat"]

        with pytest.raises(ValidationError):
            VeoliaContractDetails.model_validate(data)

    def test_unknown_fields_are_ignored(self) -> None:
        details = VeoliaContractDetails.model_validate({**contract_details(), "newField": "x"})

        assert not hasattr(details, "newField")


class TestConsumptionRecord:
    def test_reads_the_text_values(self) -> None:
        parsed = VeoliaConsumptionRecord.model_validate(record("2026-10-05", "143.868", "0.53"))

        assert parsed.consumption_m3 == Decimal("0.53")
        assert parsed.index_m3 == Decimal("143.868")
        assert parsed.date_index.isoformat() == "2026-10-05T21:00:00"
        assert parsed.estimated is False
        assert parsed.index_estimated is True
        assert parsed.permanent_flow == 0

    def test_keeps_the_precision_of_the_site(self) -> None:
        parsed = VeoliaConsumptionRecord.model_validate(record("2026-04-29", "0", "18.640625"))

        assert parsed.consumption_m3 == Decimal("18.640625")

    def test_keeps_unknown_fields(self) -> None:
        parsed = VeoliaConsumptionRecord.model_validate(record("2026-10-05", "1", "1", NEW_FIELD="x"))

        assert parsed.model_extra == {"NEW_FIELD": "x"}

    def test_estimated_flag(self) -> None:
        assert VeoliaConsumptionRecord.model_validate(record("2026-10-05", "1", "1", estimated=True)).estimated is True

    def test_missing_flags_mean_false(self) -> None:
        data = record("2026-10-05", "1", "1")
        del data["FLAG_ESTIMATION"]
        del data["FLAG_ESTIMATION_INDEX"]
        del data["DEBIT_PERMANENT"]

        parsed = VeoliaConsumptionRecord.model_validate(data)

        assert (parsed.estimated, parsed.index_estimated, parsed.permanent_flow) == (False, False, None)

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
    def test_reads_the_records_and_everything_around_them(self) -> None:
        response = VeoliaConsumptionResponse.model_validate(
            consumption([record("2026-10-05", "1", "0.1"), record("2026-10-06", "1.1", "0.1")])
        )

        assert len(response.data.records) == 2
        assert response.average_water_price == Decimal("4.9171")
        assert response.permanent_flow_threshold == 0
        assert response.shows_permanent_flow is False
        assert response.can_compare_month is True
        assert response.index_readings == ["1;2026-10-05 21:00:00", "1.1;2026-10-06 21:00:00"]
        data = response.data
        assert (data.maximum_m3, data.average_m3) == (Decimal("2.921"), Decimal("0.92921"))
        assert data.maximum_day is not None
        assert data.maximum_day.isoformat() == "2026-09-05"
        assert data.period_start is not None
        assert data.period_start.isoformat() == "2026-07-12T02:00:00"
        assert (data.meter_number, data.point_id) == ("X1", "1234567890")

    def test_the_summary_fields_are_optional(self) -> None:
        response = VeoliaConsumptionResponse.model_validate({"data": {"CONSOMMATION": []}})

        assert response.average_water_price is None
        assert response.index_readings == []
        assert response.data.maximum_day is None

    def test_the_site_sends_an_empty_text_for_a_summary_it_did_not_compute(self) -> None:
        data = VeoliaConsumptionData.model_validate(
            {"CONSOMMATION": [], "DATE_CONSOMMATION_MAX": "", "CONSOMMATION_MAX": " ", "DATE_DEBUT": ""}
        )

        assert (data.maximum_day, data.maximum_m3, data.period_start) == (None, None, None)

    def test_no_records(self) -> None:
        assert VeoliaConsumptionResponse.model_validate(consumption([])).data.records == []

    def test_needs_the_data(self) -> None:
        with pytest.raises(ValidationError):
            VeoliaConsumptionResponse.model_validate({"prixMoyenEau": 1})
