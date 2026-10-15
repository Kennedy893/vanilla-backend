from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import LotStatus, LotType, ProductState


class LotCreate(BaseModel):
    """Ce que le client envoie. Rien d'autre : holder, auteur, statut, type, code
    sont déduits par le serveur."""

    farm_id: int
    quantity_kg: Decimal = Field(gt=0, le=50_000, max_digits=15, decimal_places=2)
    harvest_date: date
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("harvest_date")
    @classmethod
    def harvest_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("La date de récolte ne peut pas être dans le futur.")
        return value


class LotRead(BaseModel):
    """Ce que l'API renvoie (construit directement depuis l'objet Lot)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    lot_code: str
    lot_type: LotType
    product_state: ProductState | None
    quantity_kg: Decimal
    status: LotStatus | None
    farm_id: int
    holder_id: int
    created_at: datetime | None
    updated_at: datetime | None