from app.services.organizations_service import get_all_organizations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.organization import OrganizationRead

router = APIRouter(prefix="/organizations", tags=["Organizations"])

@router.get("", response_model=list[OrganizationRead])
def list_all_organizations(
    db: Session = Depends(get_db),
):
    return get_all_organizations(db=db)