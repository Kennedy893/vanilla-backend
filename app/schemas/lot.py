from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

class FarmSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
 
    id: int
    farm_code: str
    name: str | None

class LotListItem(BaseModel):
    """Une ligne du tableau : le strict nécessaire, déjà jointe (pas de requête par ligne)."""
 
    id: int
    lot_code: str
    product_state: ProductState | None
    quantity_kg: Decimal  # sérialisé en chaîne dans le JSON ("120.50")
    status: LotStatus | None
    farm: FarmSummary
    harvest_date: datetime | None  # date de l'événement de récolte
    created_at: datetime | None
 
 
class LotListResponse(BaseModel):
    items: list[LotListItem]
    total: int  # nombre de lots correspondant aux filtres (pour la pagination)
    limit: int
    offset: int
    # Compteurs pour les onglets de statut : tient compte de tous les filtres SAUF le statut
    status_counts: dict[str, int]
 
 
class LotListFilters(BaseModel):
    """Paramètres de requête de GET /lots (tous optionnels)."""
 
    status: LotStatus | None = None
    product_state: ProductState | None = None
    farm_id: int | None = None
    q: str | None = Field(default=None, max_length=50, description="Recherche par code de lot")
    harvest_from: date | None = None
    harvest_to: date | None = None
    sort: Literal["harvest_date", "created_at", "lot_code", "quantity_kg"] = "harvest_date"
    order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
 
    @field_validator("q")
    @classmethod
    def blank_search_is_none(cls, value: str | None) -> str | None:
        value = value.strip() if value else value
        return value or None
 
    @model_validator(mode="after")
    def check_date_range(self) -> "LotListFilters":
        if self.harvest_from and self.harvest_to and self.harvest_from > self.harvest_to:
            raise ValueError("La date de début doit précéder la date de fin.")
        return self