"""The answers of the Veolia Apex methods, validated as they are read.

The site can change at any time, so these models stay apart from the model that users get (see model.py). They hold
what the backend sends, with its names and units: volumes and indexes are cubic meters, sent as text. The fields that
identify a person (names, mail, phone, addresses) and the opaque tokens of a meter are left out of their repr, so that
they do not reach a log by accident. The consumption records hold nothing personal, so their unknown fields are kept,
and a new field from the site does not make them invalid.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VeoliaMeter(BaseModel):
    """A meter of a contract. The two opaque tokens are what the consumption method asks for in place of the meter number."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    meter_token: str = Field(alias="ELEMB", repr=False)
    point_token: str = Field(alias="ELEMA", repr=False)
    point_id: str | None = Field(default=None, alias="ID_PDS")
    meter_number: str | None = Field(default=None, alias="NUM_COMPTEUR")


class VeoliaContract(BaseModel):
    """A contract: its number, its status, the authority that organizes the service, and the address that is served."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(alias="Id")
    number: str | None = Field(default=None, alias="Name")
    status: str | None = Field(default=None, alias="Statut")
    authority: str | None = Field(default=None, alias="AutoriteOrganisatrice")
    end_date: date | None = Field(default=None, alias="DateSortieEPT")
    street: str | None = Field(default=None, alias="SITE_Rue", repr=False)
    postal_code: str | None = Field(default=None, alias="SITE_CP", repr=False)
    city: str | None = Field(default=None, alias="SITE_Commune", repr=False)


class VeoliaParty(BaseModel):
    """The customer or the payer of a contract. All of it is personal data."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = Field(default=None, alias="Id", repr=False)
    contract_client_id: str | None = Field(default=None, alias="ContratClientId", repr=False)
    crm_id: str | None = Field(default=None, alias="VCRM_ID", repr=False)
    name: str | None = Field(default=None, alias="Name", repr=False)
    salutation: str | None = Field(default=None, alias="Salutation", repr=False)
    first_name: str | None = Field(default=None, alias="FirstName", repr=False)
    last_name: str | None = Field(default=None, alias="LastName", repr=False)
    email: str | None = Field(default=None, alias="Email", repr=False)
    mobile_phone: str | None = Field(default=None, alias="MobilePhone", repr=False)
    billing_street: str | None = Field(default=None, alias="BillingStreet", repr=False)
    billing_postal_code: str | None = Field(default=None, alias="BillingPostalCode", repr=False)
    billing_city: str | None = Field(default=None, alias="BillingCity", repr=False)
    vat_liable: bool | None = Field(default=None, alias="AssujettiTVA")
    large_account: bool | None = Field(default=None, alias="GC")
    locked: bool | None = Field(default=None, alias="VerrouillageFiche")


class VeoliaContractDetails(BaseModel):
    """The details of a contract."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    contract: VeoliaContract = Field(alias="contrat")
    meters: list[VeoliaMeter] = Field(alias="compteInfo", min_length=1)
    customer: VeoliaParty | None = Field(default=None, alias="contratClient")
    payer: VeoliaParty | None = Field(default=None, alias="payeurClient")
    is_individual: bool | None = Field(default=None, alias="compteParticulier")
    has_multiple_contracts: bool | None = Field(default=None, alias="multipleContrats")
    segment: str | None = Field(default=None, alias="segmentationPrimaire")
    balance: Decimal | None = Field(default=None, alias="solde")


class VeoliaConsumptionRecord(BaseModel):
    """One period of consumption: a day, a week or a month. The volumes are cubic meters, sent as text."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    date_index: datetime = Field(alias="DATE_INDEX")
    consumption_m3: Decimal = Field(alias="CONSOMMATION")
    index_m3: Decimal = Field(alias="VALEUR_INDEX")
    estimated: bool = Field(default=False, alias="FLAG_ESTIMATION")
    index_estimated: bool = Field(default=False, alias="FLAG_ESTIMATION_INDEX")
    permanent_flow: Decimal | None = Field(default=None, alias="DEBIT_PERMANENT")

    @field_validator("consumption_m3")
    @classmethod
    def check_not_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("the consumption is negative")

        return value


class VeoliaConsumptionData(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    records: list[VeoliaConsumptionRecord] = Field(alias="CONSOMMATION")
    period_start: datetime | None = Field(default=None, alias="DATE_DEBUT")
    period_end: datetime | None = Field(default=None, alias="DATE_FIN")
    meter_number: str | None = Field(default=None, alias="NUMERO_COMPTEUR")
    point_id: str | None = Field(default=None, alias="ID_PDS")
    maximum_m3: Decimal | None = Field(default=None, alias="CONSOMMATION_MAX")
    maximum_day: date | None = Field(default=None, alias="DATE_CONSOMMATION_MAX")
    average_m3: Decimal | None = Field(default=None, alias="CONSOMMATION_MOYENNE")

    @field_validator("period_start", "period_end", "maximum_m3", "maximum_day", "average_m3", mode="before")
    @classmethod
    def empty_means_missing(cls, value: Any) -> Any:
        """The site sends an empty text for a summary that it did not compute, for instance the day of the maximum."""

        return None if isinstance(value, str) and not value.strip() else value


class VeoliaConsumptionResponse(BaseModel):
    """The answer of the consumption history method."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    data: VeoliaConsumptionData
    average_water_price: Decimal | None = Field(default=None, alias="prixMoyenEau")
    permanent_flow_threshold: Decimal | None = Field(default=None, alias="seuilDebitPermanet")
    shows_permanent_flow: bool = Field(default=False, alias="showDebitPermanent")
    can_compare_month: bool = Field(default=False, alias="canCompareMonth")
    # Each item is "index;date", for instance "62.642;2026-07-12 21:00:00": the readings of the meter.
    index_readings: list[str] = Field(default_factory=list, alias="indexMesure")
