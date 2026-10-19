from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    location_type: str | None
    latitude: Decimal | None
    longitude: Decimal | None