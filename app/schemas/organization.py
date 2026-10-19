from datetime import datetime

from pydantic import BaseModel, ConfigDict

class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    organization_type: str | None
    created_at: datetime | None