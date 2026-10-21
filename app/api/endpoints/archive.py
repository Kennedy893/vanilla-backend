from app.models import Lot, User
from app.schemas.lot import LotArchive, LotRead
from app.services.archive_service import archive_lot, unarchive_lot
from app.services.lot_rules import LotStateError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dependencies import OrgContext, get_org_context

router = APIRouter(prefix="/lots", tags=["Lots"])

@router.post("/{lot_id}/archive", response_model=LotRead)
def archive_lot_endpoint(
    lot_id: int,
    data: LotArchive,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context)
):
    """Archive un lot (organisation propriétaire uniquement)."""
    try:
        return archive_lot(
            db=db,
            lot_id=lot_id,
            data=data,
            user=ctx.user,
            organization=ctx.organization,
            role=ctx.role,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LotStateError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.post("/{lot_id}/unarchive", response_model=LotRead)
def unarchive_lot_endpoint(
    lot_id: int,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Désarchive un lot (owner uniquement). Aucun corps de requête."""
    try:
        return unarchive_lot(
            db=db,
            lot_id=lot_id,
            organization=ctx.organization,
            role=ctx.role,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LotStateError as e:
        raise HTTPException(status_code=409, detail=str(e))