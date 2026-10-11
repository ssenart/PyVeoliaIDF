"""The data model of pyveoliaidf: what users get.

It follows what the Veolia backend offers: contracts with their meters and parties, and consumption histories by day,
week or month. Volumes and indexes are cubic meters (Decimal), as the backend sends them, with liters and euros derived.
The fields that identify a person or a place are left out of the repr, so that they do not reach a log by accident.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

LITERS_PER_CUBIC_METER = Decimal(1000)


# ------------------------------------------------------------------------------------------------------------
class Step(str, Enum):
    """The step of a consumption history: what one reading covers."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


# ------------------------------------------------------------------------------------------------------------
class Reading(BaseModel):
    """The consumption of one period, with the index of the meter at its end.

    The period is a day, a week (Monday to Sunday) or a month, depending on the step of the history. day is the last day
    of the period, and time is the moment of the reading, as the site sends it. The time of day is not a clock time that
    the site documents, so use day to place a reading on the calendar.
    """

    model_config = ConfigDict(frozen=True)

    day: date
    time: datetime
    volume_m3: Decimal
    index_m3: Decimal
    estimated: bool = False
    index_estimated: bool = False
    permanent_flow: Decimal | None = None
    meter_changed: bool = False
    cost_eur: Decimal | None = None

    @property
    def liters(self) -> Decimal:
        return self.volume_m3 * LITERS_PER_CUBIC_METER

    @property
    def index_liters(self) -> Decimal:
        return self.index_m3 * LITERS_PER_CUBIC_METER


# ------------------------------------------------------------------------------------------------------------
class MeterIndex(BaseModel):
    """A reading of the index of the meter: the "relevés" of the site."""

    model_config = ConfigDict(frozen=True)

    index_m3: Decimal
    time: datetime


# ------------------------------------------------------------------------------------------------------------
class Meter(BaseModel):
    """A meter of a contract."""

    model_config = ConfigDict(frozen=True)

    number: str | None
    point_id: str | None
    # The opaque tokens that the site asks for when it reads the meter.
    meter_token: str = Field(repr=False)
    point_token: str = Field(repr=False)


# ------------------------------------------------------------------------------------------------------------
class Site(BaseModel):
    """The address that a contract serves."""

    model_config = ConfigDict(frozen=True)

    street: str | None = Field(repr=False)
    postal_code: str | None = Field(repr=False)
    city: str | None = Field(repr=False)


# ------------------------------------------------------------------------------------------------------------
class Party(BaseModel):
    """The customer or the payer of a contract. All of it is personal data."""

    model_config = ConfigDict(frozen=True)

    id: str | None = Field(repr=False)
    contract_client_id: str | None = Field(repr=False)
    crm_id: str | None = Field(repr=False)
    name: str | None = Field(repr=False)
    salutation: str | None = Field(repr=False)
    first_name: str | None = Field(repr=False)
    last_name: str | None = Field(repr=False)
    email: str | None = Field(repr=False)
    mobile_phone: str | None = Field(repr=False)
    billing_street: str | None = Field(repr=False)
    billing_postal_code: str | None = Field(repr=False)
    billing_city: str | None = Field(repr=False)
    vat_liable: bool | None
    large_account: bool | None
    locked: bool | None


# ------------------------------------------------------------------------------------------------------------
class Contract(BaseModel):
    """A contract of the account, with its meters.

    The number is what identifies a contract: it is stable, so keep it and pass it back to the client. The id is an
    opaque token that the site makes anew at each call (and so are the tokens of the meters): never store it.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    number: str | None
    status: str | None
    authority: str | None
    end_date: date | None
    site: Site
    meters: list[Meter]
    customer: Party | None
    payer: Party | None
    is_individual: bool | None
    has_multiple_contracts: bool | None
    segment: str | None
    balance: Decimal | None


# ------------------------------------------------------------------------------------------------------------
class ConsumptionHistory(BaseModel):
    """The readings of a meter over a period, with what the site says about them."""

    model_config = ConfigDict(frozen=True)

    contract_number: str | None
    meter_number: str | None
    point_id: str | None
    step: Step
    start: date
    end: date
    # The period that the site says it covered (the first and the last of its windows).
    period_start: datetime | None
    period_end: datetime | None
    readings: list[Reading]
    # The index of the meter at each reading date.
    meter_readings: list[MeterIndex]
    average_price_eur_m3: Decimal | None
    permanent_flow_threshold: Decimal | None
    shows_permanent_flow: bool
    can_compare_month: bool
    retrieved_at: datetime

    @property
    def total_m3(self) -> Decimal:
        return sum((reading.volume_m3 for reading in self.readings), Decimal(0))

    @property
    def total_cost_eur(self) -> Decimal | None:
        if self.average_price_eur_m3 is None:
            return None

        return self.total_m3 * self.average_price_eur_m3

    @property
    def average_m3(self) -> Decimal | None:
        """The average volume of a reading: the "consommation moyenne" of the site."""

        return self.total_m3 / len(self.readings) if self.readings else None

    @property
    def minimum(self) -> Reading | None:
        """The reading with the lowest volume: the "consommation minimum" of the site."""

        return min(self.readings, key=lambda reading: reading.volume_m3, default=None)

    @property
    def maximum(self) -> Reading | None:
        """The reading with the highest volume: the "consommation maximum" of the site."""

        return max(self.readings, key=lambda reading: reading.volume_m3, default=None)
