from typing import List

from app.database import get_db
from app.schemas.lot import LotCreate, LotHistoryEvent, LotListFilters, LotListResponse, LotRead
from app.services.dependencies import OrgContext, get_org_context
from app.services.lots_service import LotStateError, create_lot, get_lots, validate_lot
from app.services.traceability_service import get_lots_historical
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session


router = APIRouter(prefix="/lots", tags=["Lots"])

@router.post("", response_model=LotRead, status_code=201)
def create_lot_endpoint(
    data: LotCreate,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Crée un lot de récolte.

    Args:
        data: Les données du lot à créer.
        db: La session de base de données.
        user: L'utilisateur authentifié.

    Returns:
        Le lot créé (sérialisé avec LotRead).

    Raises:
        HTTPException: Si l'utilisateur n'a pas les droits nécessaires ou si la ferme n'existe pas.
    """
    try:
        lot = create_lot(
            db=db,
            data=data,
            user=ctx.user,
            organization=ctx.organization,
            role=ctx.role,
        )
        return lot
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("", response_model=LotListResponse)
def list_lots_endpoint(
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
    filters: LotListFilters = Depends(),
):
    """
    Liste les lots de récolte avec pagination et filtres.

    Args:
        db: La session de base de données.
        ctx: Le contexte de l'organisation et de l'utilisateur.
        filters: Les filtres pour la liste des lots.

    Returns:
        Une réponse contenant la liste des lots et le total.
    """
    try:
        response = get_lots(db=db, organization=ctx.organization, filters=filters)
        return response
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("/{lot_id}/history", response_model=List[LotHistoryEvent])
def get_lot_history_endpoint(
    lot_id: int,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Récupère l'historique d'un lot spécifique.

    Args:
        lot_id: L'identifiant du lot.
        db: La session de base de données.
        ctx: Le contexte de l'organisation et de l'utilisateur.

    Returns:
        Une liste d'événements historiques du lot.

    Raises:
        HTTPException: Si le lot n'existe pas ou si l'utilisateur n'a pas les droits nécessaires.
    """
    try:
        history = get_lots_historical(db=db, organization=ctx.organization, lot_id=lot_id)
        return history
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{lot_id}/validate", response_model=LotRead)
def validate_lot_endpoint(
    lot_id: int,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """
    Valide un lot de récolte.

    Args:
        lot_id: L'identifiant du lot à valider.
        db: La session de base de données.
        ctx: Le contexte de l'organisation et de l'utilisateur.

    Returns:
        Le lot validé (sérialisé avec LotRead).

    Raises:
        HTTPException: Si le lot n'existe pas ou si l'utilisateur n'a pas les droits nécessaires.
    """
    try:
        lot = validate_lot(db=db, organization=ctx.organization, user=ctx.user, role=ctx.role, lot_id=lot_id)
        return lot
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LotStateError as e:
        raise HTTPException(status_code=409, detail=str(e))