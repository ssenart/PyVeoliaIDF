"""The data model of PyVeoliaIDF: the readings that users get.

The aliases are the keys of the dict form: they are the values of PropertyNameEnum, which the Home Assistant integration reads.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

MEASURED = "Mesuré"
ESTIMATED = "Estimé"


class DailyReading(BaseModel):
    """The water consumption of one day, with the index of the meter at the end of it. The volumes are liters."""

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    time: datetime = Field(alias="time")
    total_liter: int = Field(alias="total_liter", ge=0)
    daily_liter: int = Field(alias="daily_liter", ge=0)
    type: str = Field(alias="type")
    timestamp: str = Field(alias="timestamp")

    @field_serializer("time")
    def serialize_time(self, value: datetime) -> str:
        return value.strftime(TIME_FORMAT)

    def as_dict(self) -> dict[str, Any]:
        """Returns the reading as the dict that the users of the library read: the keys are the PropertyNameEnum values."""

        return self.model_dump(by_alias=True)
