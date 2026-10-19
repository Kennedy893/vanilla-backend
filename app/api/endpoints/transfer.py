from app.models import Lot, MemberRole, TraceabilityEvent, Transfer, TransferStatus, User
from app.schemas.transfer import PendingTransferItem, TransferRead, TransferReceive, TransferReject
from app.services.auth_service import get_current_user
from app.services.dependencies import OrgContext, get_org_context
from app.services.lots_service import LotStateError
from app.services.transfers_service import get_pending_transfers, reject_transfer, validate_transfer
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/pending_transfers", tags=["Pending Transfers"])

@router.get("", response_model=list[PendingTransferItem])
def list_pending_transfers(
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context)
):
    """Liste les transferts en attente de réception (tous les rôles peuvent lire)."""
    return get_pending_transfers(db=db, organization=ctx.organization)

@router.post("/{transfer_id}/validate", response_model=TransferRead)
def validate_transfer_endpoint(
    transfer_id: int,
    data: TransferReceive,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Confirme la réception d'un transfert (organisation destinataire uniquement)."""
    try:
        return validate_transfer(
            db=db,
            transfer_id=transfer_id,
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
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
 
 
@router.post("/{transfer_id}/reject", response_model=TransferRead)
def reject_transfer_endpoint(
    transfer_id: int,
    data: TransferReject,
    db: Session = Depends(get_db),
    ctx: OrgContext = Depends(get_org_context),
):
    """Refuse la réception d'un transfert, avec un motif obligatoire."""
    try:
        return reject_transfer(
            db=db,
            transfer_id=transfer_id,
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