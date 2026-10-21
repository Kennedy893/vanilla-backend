from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

def _clean(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value

class FarmRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    farm_code: str
    name: str | None
    area_hectares: Decimal | None
    location_id: int
    producer_organization_id: int
    created_at: datetime | None

class FarmCreate(BaseModel):
    """Création d'une exploitation. Le code et l'organisation ne sont jamais saisis."""
 
    name: str = Field(min_length=1, max_length=50)
    area_hectares: Decimal | None = Field(default=None, gt=0, le=10_000, max_digits=15, decimal_places=2)
    location_name: str = Field(min_length=1, max_length=50)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)
 
    @field_validator("name", "location_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ce champ est obligatoire.")
        return value
 
    @model_validator(mode="after")
    def coordinates_go_together(self) -> "FarmCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("La latitude et la longitude vont ensemble.")
        return self
 
 
class FarmUpdate(BaseModel):
    """Modification partielle : seuls les champs envoyés sont modifiés.
 
    Envoyer `"area_hectares": null` efface la surface ; ne pas envoyer le champ la laisse telle quelle.
    Le code et l'organisation propriétaire ne sont pas modifiables.
    """
 
    name: str | None = Field(default=None, min_length=1, max_length=50)
    area_hectares: Decimal | None = Field(default=None, gt=0, le=10_000, max_digits=15, decimal_places=2)
    location_name: str | None = Field(default=None, min_length=1, max_length=50)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)
 
    @model_validator(mode="after")
    def check_consistency(self) -> "FarmUpdate":
        provided = self.model_fields_set
        if not provided:
            raise ValueError("Aucune modification fournie.")
        for field in ("name", "location_name"):
            if field in provided:
                value = _clean(getattr(self, field))
                if not value:
                    raise ValueError("Ce champ ne peut pas être vide.")
                setattr(self, field, value)
        if ("latitude" in provided) != ("longitude" in provided):
            raise ValueError("La latitude et la longitude vont ensemble.")
        if ("latitude" in provided) and ((self.latitude is None) != (self.longitude is None)):
            raise ValueError("La latitude et la longitude vont ensemble.")
        return self
 
 
class FarmListItem(BaseModel):
    """Une ligne du tableau « Exploitations »."""
 
    id: int
    farm_code: str
    name: str | None
    area_hectares: Decimal | None  # chaîne dans le JSON
    location_name: str
    latitude: Decimal | None
    longitude: Decimal | None
    lots_count: int  # tous les lots issus de l'exploitation, archivés compris
    created_at: datetime | None
 
 
class FarmListResponse(BaseModel):
    items: list[FarmListItem]
    total: int
    limit: int
    offset: int