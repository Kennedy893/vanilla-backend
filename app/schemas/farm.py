from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FarmRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    farm_code: str
    name: str | None
    area_hectares: Decimal | None
    location_id: int
    producer_organization_id: int
    created_at: datetime | None