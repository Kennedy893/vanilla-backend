from datetime import datetime, time

from app.services.lots_service import generate_event_code
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    EventLot,
    EventLotRole,
    EventStatus,
    EventType,
    Farm,
    Location,
    Lot,
    LotStatus,
    MemberRole,
    Organization,
    TraceabilityEvent,
    Transfer,
    TransferStatus,
    User,
)
from app.schemas.transfer import LotStateError, TransferCreate

TRANSFER_ROLES = {MemberRole.OPERATOR, MemberRole.MANAGER, MemberRole.OWNER}


def transfer_lot(
    db: Session,
    lot_id: int,
    data: TransferCreate,
    user: User,
    organization: Organization,
    role: MemberRole,
) -> Transfer:
    """Dispatch a whole lot to another organization (step 1 of 2: the reception comes later).

    The lot becomes IN_TRANSFER and stays held by the sender until the receiver confirms.

    Raises:
        PermissionError: the role cannot transfer lots (-> 403).
        LookupError: lot, destination organization or destination location not found (-> 404).
        LotStateError: the lot is not AVAILABLE (-> 409).
        ValueError: invalid data (same organization, date before the harvest) (-> 422).
    """
    if role not in TRANSFER_ROLES:
        raise PermissionError("Votre rôle ne permet pas de transférer un lot.")

    # Le lot est verrouillé : deux transferts simultanés du même lot sont impossibles
    lot = db.scalar(
        select(Lot)
        .where(Lot.id == lot_id, Lot.holder_id == organization.id)
        .with_for_update()
    )
    if lot is None:
        raise LookupError("Lot introuvable.")
    if lot.status != LotStatus.AVAILABLE:
        raise LotStateError("Seul un lot disponible peut être transféré.")
    if lot.quantity_kg <= 0:
        raise LotStateError("Un lot vide ne peut pas être transféré.")

    # Destinataire et lieu de destination
    if data.to_organization_id == organization.id:
        raise ValueError("L'organisation destinataire doit être différente de la vôtre.")
    destination = db.get(Organization, data.to_organization_id)
    if destination is None or not destination.is_active:
        raise LookupError("Organisation destinataire introuvable.")
    if db.get(Location, data.destination_location_id) is None:
        raise LookupError("Lieu de destination introuvable.")

    # Pas d'expédition avant la récolte
    harvest_date = db.scalar(
        select(func.min(TraceabilityEvent.event_date))
        .join(EventLot, EventLot.event_id == TraceabilityEvent.id)
        .where(EventLot.lot_id == lot.id, TraceabilityEvent.event_type == EventType.HARVEST)
    )
    dispatch_at = datetime.combine(data.dispatch_date, time.min)
    if harvest_date is not None and dispatch_at < harvest_date:
        raise ValueError("La date d'expédition ne peut pas précéder la récolte.")

    # Lieu d'origine : déduit, jamais saisi. C'est le lieu du dernier événement validé du lot ;
    # à défaut, le lieu de son exploitation.
    origin_location_id = db.scalar(
        select(TraceabilityEvent.location_id)
        .join(EventLot, EventLot.event_id == TraceabilityEvent.id)
        .where(EventLot.lot_id == lot.id, TraceabilityEvent.status == EventStatus.VALIDATED)
        .order_by(TraceabilityEvent.event_date.desc(), TraceabilityEvent.id.desc())
        .limit(1)
    )
    if origin_location_id is None:
        origin_location_id = db.get(Farm, lot.farm_id).location_id

    # Tout ou rien : événement + transfert + liaison + changement de statut du lot
    try:
        event = TraceabilityEvent(
            event_code=generate_event_code(db),
            event_type=EventType.TRANSFER,
            event_date=dispatch_at,
            description=data.notes,
            status=EventStatus.PENDING,  # sera validé par le destinataire à la réception
            recorded_by_id=user.id,
            location_id=origin_location_id,
            organization_id=organization.id,
        )
        db.add(event)
        db.flush()

        transfer = Transfer(
            event_id=event.id,
            dispatch_date=dispatch_at,
            status=TransferStatus.DISPATCHED,
            from_organization_id=organization.id,
            to_organization_id=destination.id,
            origin_location_id=origin_location_id,
            destination_location_id=data.destination_location_id,
        )
        db.add(transfer)

        db.add(
            EventLot(
                event_id=event.id,
                lot_id=lot.id,
                role=EventLotRole.TRANSFERRED,
                quantity_kg=lot.quantity_kg,  # lot entier
            )
        )

        lot.status = LotStatus.IN_TRANSFER  # le détenteur ne change qu'à la réception
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(transfer)
    return transfer