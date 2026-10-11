"""The answers of the Veolia Apex methods, validated as they are read.

The site can change at any time, so these models stay apart from the model that users get (see model.py). They keep only
what the library needs: the contract details also hold the name, address, phone and mail of the customer, which must not
travel through the library, so the unknown fields of the details are dropped. The consumption records hold nothing
personal, so their unknown fields are kept, and a new field from the site does not make them invalid.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VeoliaMeter(BaseModel):
    """A meter of a contract. The two opaque tokens are what the consumption method asks for in place of the meter number."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    meter_token: str = Field(alias="ELEMB", repr=False)
    point_token: str = Field(alias="ELEMA", repr=False)
    meter_number: str | None = Field(default=None, alias="NUM_COMPTEUR")


class VeoliaContract(BaseModel):
    """The part of a contract that identifies it."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(alias="Id")
    name: str | None = Field(default=None, alias="Name")


class VeoliaContractDetails(BaseModel):
    """The details of a contract, reduced to its identity and its meters."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    contract: VeoliaContract = Field(alias="contrat")
    meters: list[VeoliaMeter] = Field(alias="compteInfo", min_length=1)


class VeoliaConsumptionRecord(BaseModel):
    """One day of consumption. The volumes are cubic meters, sent as text."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    date_index: datetime = Field(alias="DATE_INDEX")
    consumption_m3: Decimal = Field(alias="CONSOMMATION")
    index_m3: Decimal = Field(alias="VALEUR_INDEX")
    estimated: bool = Field(default=False, alias="FLAG_ESTIMATION")

    @field_validator("consumption_m3")
    @classmethod
    def check_not_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("the consumption is negative")

        return value


class VeoliaConsumptionData(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    records: list[VeoliaConsumptionRecord] = Field(alias="CONSOMMATION")


class VeoliaConsumptionResponse(BaseModel):
    """The answer of the consumption history method."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    data: VeoliaConsumptionData
    average_water_price: Decimal | None = Field(default=None, alias="prixMoyenEau")
