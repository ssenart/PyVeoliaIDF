from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pyveoliaidf import ConsumptionHistory, Reading, Step


def reading(day: int, volume: str, index: str = "1", cost: str | None = None) -> Reading:
    return Reading(
        day=date(2026, 1, day),
        time=datetime(2026, 1, day, 21),
        volume_m3=Decimal(volume),
        index_m3=Decimal(index),
        cost_eur=Decimal(cost) if cost else None,
    )


def history(*readings: Reading, price: str | None = "5") -> ConsumptionHistory:
    return ConsumptionHistory(
        contract_number="C",
        meter_number="X1",
        point_id="1",
        step=Step.DAY,
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        period_start=None,
        period_end=None,
        readings=list(readings),
        meter_readings=[],
        average_price_eur_m3=Decimal(price) if price else None,
        permanent_flow_threshold=None,
        shows_permanent_flow=False,
        can_compare_month=False,
        retrieved_at=datetime(2026, 2, 1),
    )


class TestReading:
    def test_is_immutable(self) -> None:
        with pytest.raises(ValidationError):
            reading(1, "1").volume_m3 = Decimal(2)

    def test_liters_are_derived_exactly(self) -> None:
        assert reading(1, "0.374", "144.242").liters == Decimal("374")
        assert reading(1, "0.374", "144.242").index_liters == Decimal("144242")

    def test_json_keeps_decimals_exact(self) -> None:
        assert reading(1, "18.640625").model_dump(mode="json")["volume_m3"] == "18.640625"


class TestConsumptionHistory:
    def test_summary_like_the_site(self) -> None:
        summary = history(reading(1, "0.5"), reading(2, "2.5"), reading(3, "1.0"))

        assert summary.total_m3 == Decimal("4.0")
        assert summary.average_m3 == Decimal("4.0") / 3
        assert summary.minimum is not None and summary.minimum.day == date(2026, 1, 1)
        assert summary.maximum is not None and summary.maximum.day == date(2026, 1, 2)
        assert summary.total_cost_eur == Decimal("20.0")

    def test_empty_history(self) -> None:
        empty = history()

        assert empty.total_m3 == 0
        assert empty.average_m3 is None
        assert empty.minimum is None
        assert empty.maximum is None

    def test_no_price_means_no_total_cost(self) -> None:
        assert history(reading(1, "1"), price=None).total_cost_eur is None

    def test_step_values(self) -> None:
        assert [step.value for step in Step] == ["day", "week", "month"]
