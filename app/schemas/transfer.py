from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import TransferStatus


class TransferCreate(BaseModel):
    """Ce que le client envoie pour expédier un lot (le lot vient de l'URL)."""

    to_organization_id: int
    destination_location_id: int
    dispatch_date: date
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("dispatch_date")
    @classmethod
    def dispatch_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("La date d'expédition ne peut pas être dans le futur.")
        return value


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: TransferStatus
    dispatch_date: datetime | None
    receipt_date: datetime | None
    from_organization_id: int
    to_organization_id: int
    origin_location_id: int
    destination_location_id: int
    event_id: int

class LotStateError(Exception):
    """Le lot n'est pas dans un état qui permet cette action (-> 409)."""