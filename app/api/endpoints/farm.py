from http.client import HTTPException

from app.services.exceptions import ConflictError
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dependencies import OrgContext, get_org_context
from app.schemas.farm import FarmCreate, FarmListResponse, FarmRead, FarmUpdate
from app.services.farms_service import create_farm, delete_farm, get_farms_by_organization, get_farms_list, update_farm

router = APIRouter(prefix="/farms", tags=["Farms"])


@router.get("", response_model=list[FarmRead])
def list_farms(
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Liste les exploitations de l'organisation active (tous les rôles peuvent lire)."""
    return get_farms_by_organization(db=db, organization=ctx.organization)

# Liste enrichie et paginée : alimente la page « Exploitations »
@router.get("/list", response_model=FarmListResponse)
def list_farms_page(
    q: str | None = Query(default=None, max_length=50, description="Recherche par nom ou code"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Exploitations avec localité, coordonnées et nombre de lots (tous les rôles peuvent lire)."""
    return get_farms_list(
        db=db,
        organization=ctx.organization,
        q=q,
        limit=limit,
        offset=offset,
    )

@router.post("", response_model=FarmRead, status_code=201)
def create_farm_endpoint(
    data: FarmCreate,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Crée une exploitation et son lieu (manager ou owner). Le code est généré par le serveur."""
    try:
        return create_farm(
            db=db,
            data=data,
            organization=ctx.organization,
            role=ctx.role,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.patch("/{farm_id}", response_model=FarmRead)
def update_farm_endpoint(
    farm_id: int,
    data: FarmUpdate,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Modifie le nom, la surface ou le lieu d'une exploitation (manager ou owner).
    Seuls les champs envoyés sont modifiés ; le code ne change jamais."""
    try:
        return update_farm(
            db=db,
            farm_id=farm_id,
            data=data,
            organization=ctx.organization,
            role=ctx.role,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.delete("/{farm_id}", status_code=204)
def delete_farm_endpoint(
    farm_id: int,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Supprime une exploitation sans aucun lot (manager ou owner)."""
    try:
        delete_farm(
            db=db,
            farm_id=farm_id,
            organization=ctx.organization,
            role=ctx.role,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))