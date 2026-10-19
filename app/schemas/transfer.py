from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ProductState, TransferStatus


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

class TransferReceive(BaseModel):
    """Confirmation de réception par l'organisation destinataire."""
 
    receipt_date: date
 
    @field_validator("receipt_date")
    @classmethod
    def receipt_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("La date de réception ne peut pas être dans le futur.")
        return value
 
 
class TransferReject(BaseModel):
    """Refus de réception : le motif est obligatoire pour que l'expéditeur comprenne."""
 
    reason: str = Field(min_length=3, max_length=500)
 
    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Le motif du refus est obligatoire.")
        return value

class PendingTransferItem(BaseModel):
    """Une ligne de la liste « Transferts à réceptionner »."""
 
    transfer_id: int  # l'identifiant à envoyer aux routes validate / reject
    event_code: str
    dispatch_date: datetime | None
    from_organization_id: int
    from_organization_name: str | None
    sent_by: str  # nom d'utilisateur de l'expéditeur
    origin_location_name: str
    destination_location_name: str
    notes: str | None
    lot_id: int
    lot_code: str
    quantity_kg: Decimal  # sérialisé en chaîne dans le JSON
    product_state: ProductState | None