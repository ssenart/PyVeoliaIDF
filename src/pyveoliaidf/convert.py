"""The conversion from the raw answers of the site (veolia_models.py) to the model that users get (model.py)."""

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

from pyveoliaidf.errors import UnexpectedResponseError
from pyveoliaidf.model import (
    ConsumptionHistory,
    Contract,
    Meter,
    MeterIndex,
    Party,
    Reading,
    Site,
    Step,
)
from pyveoliaidf.veolia_models import (
    VeoliaConsumptionRecord,
    VeoliaConsumptionResponse,
    VeoliaContractDetails,
    VeoliaMeter,
    VeoliaParty,
)

INDEX_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# ------------------------------------------------------------------------------------------------------------
def to_meter(meter: VeoliaMeter) -> Meter:
    return Meter(
        number=meter.meter_number,
        point_id=meter.point_id,
        meter_token=meter.meter_token,
        point_token=meter.point_token,
    )


# ------------------------------------------------------------------------------------------------------------
def to_party(party: VeoliaParty | None) -> Party | None:
    if party is None:
        return None

    return Party(
        id=party.id,
        contract_client_id=party.contract_client_id,
        crm_id=party.crm_id,
        name=party.name,
        salutation=party.salutation,
        first_name=party.first_name,
        last_name=party.last_name,
        email=party.email,
        mobile_phone=party.mobile_phone,
        billing_street=party.billing_street,
        billing_postal_code=party.billing_postal_code,
        billing_city=party.billing_city,
        vat_liable=party.vat_liable,
        large_account=party.large_account,
        locked=party.locked,
    )


# ------------------------------------------------------------------------------------------------------------
def to_contract(details: VeoliaContractDetails) -> Contract:
    contract = details.contract

    return Contract(
        id=contract.id,
        number=contract.number,
        status=contract.status,
        authority=contract.authority,
        end_date=contract.end_date,
        site=Site(street=contract.street, postal_code=contract.postal_code, city=contract.city),
        meters=[to_meter(meter) for meter in details.meters],
        customer=to_party(details.customer),
        payer=to_party(details.payer),
        is_individual=details.is_individual,
        has_multiple_contracts=details.has_multiple_contracts,
        segment=details.segment,
        balance=details.balance,
    )


# ------------------------------------------------------------------------------------------------------------
def to_reading(record: VeoliaConsumptionRecord, price: Decimal | None) -> Reading:
    """Converts a raw consumption record. The day is the date of the record, which is the day that the site shows."""

    return Reading(
        day=record.date_index.date(),
        time=record.date_index,
        volume_m3=record.consumption_m3,
        index_m3=record.index_m3,
        estimated=record.estimated,
        index_estimated=record.index_estimated,
        permanent_flow=record.permanent_flow,
        cost_eur=record.consumption_m3 * price if price is not None else None,
    )


# ------------------------------------------------------------------------------------------------------------
def parse_index_reading(text: str) -> MeterIndex:
    """Parses an item of the index readings: "62.642;2026-07-12 21:00:00"."""

    index, separator, moment = text.partition(";")
    if not separator:
        raise UnexpectedResponseError("An index reading is not in the form 'index;date'.")

    try:
        return MeterIndex(index_m3=Decimal(index), time=datetime.strptime(moment, INDEX_TIME_FORMAT))
    except (ArithmeticError, ValueError) as error:
        raise UnexpectedResponseError("An index reading is malformed.") from error


# ------------------------------------------------------------------------------------------------------------
def flag_meter_changes(readings: Sequence[Reading]) -> list[Reading]:
    """Marks the readings where the index of the meter goes down: the meter has been replaced or reset."""

    result: list[Reading] = []
    for position, reading in enumerate(readings):
        changed = position > 0 and reading.index_m3 < readings[position - 1].index_m3
        result.append(reading.model_copy(update={"meter_changed": changed}))

    return result


# ------------------------------------------------------------------------------------------------------------
def windows(start: date, end: date, size: int) -> list[tuple[date, date]]:
    """Cuts the range from start to end (both included) in consecutive windows of at most size days."""

    if size < 1:
        raise ValueError("The size of a window must be at least one day.")

    result: list[tuple[date, date]] = []
    first = start
    while first <= end:
        last = min(first + timedelta(days=size - 1), end)
        result.append((first, last))
        first = last + timedelta(days=1)

    return result


# ------------------------------------------------------------------------------------------------------------
def build_history(
    contract_number: str | None,
    meter: Meter,
    step: Step,
    start: date,
    end: date,
    responses: Iterable[VeoliaConsumptionResponse],
    retrieved_at: datetime,
) -> ConsumptionHistory:
    """Merges the answers of the windows into one history.

    A daily history keeps only the days of the range: the site answers with the day that precedes the start. The
    readings are merged by time (a reading that two windows share appears once), and sorted.
    """

    answers = list(responses)
    price = next(
        (answer.average_water_price for answer in reversed(answers) if answer.average_water_price is not None), None
    )

    records: dict[datetime, VeoliaConsumptionRecord] = {}
    index_readings: dict[datetime, MeterIndex] = {}
    for answer in answers:
        for record in answer.data.records:
            if step == Step.DAY and not start <= record.date_index.date() <= end:
                continue
            records[record.date_index] = record
        for text in answer.index_readings:
            reading = parse_index_reading(text)
            if step != Step.DAY or start <= reading.time.date() <= end:
                index_readings[reading.time] = reading

    readings = flag_meter_changes([to_reading(records[time], price) for time in sorted(records)])
    starts = [answer.data.period_start for answer in answers if answer.data.period_start is not None]
    ends = [answer.data.period_end for answer in answers if answer.data.period_end is not None]
    last = answers[-1] if answers else None

    return ConsumptionHistory(
        contract_number=contract_number,
        meter_number=next((a.data.meter_number for a in answers if a.data.meter_number), meter.number),
        point_id=next((a.data.point_id for a in answers if a.data.point_id), meter.point_id),
        step=step,
        start=start,
        end=end,
        period_start=min(starts) if starts else None,
        period_end=max(ends) if ends else None,
        readings=readings,
        meter_readings=[index_readings[time] for time in sorted(index_readings)],
        average_price_eur_m3=price,
        permanent_flow_threshold=last.permanent_flow_threshold if last else None,
        shows_permanent_flow=last.shows_permanent_flow if last else False,
        can_compare_month=last.can_compare_month if last else False,
        retrieved_at=retrieved_at,
    )
