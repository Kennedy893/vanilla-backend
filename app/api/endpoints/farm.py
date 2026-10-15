from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dependencies import OrgContext, get_org_context
from app.schemas.farm import FarmRead
from app.services.farms_service import get_farms_by_organization

router = APIRouter(prefix="/farms", tags=["Farms"])


@router.get("", response_model=list[FarmRead])
def list_farms(
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Liste les exploitations de l'organisation active (tous les rôles peuvent lire)."""
    return get_farms_by_organization(db=db, organization=ctx.organization)