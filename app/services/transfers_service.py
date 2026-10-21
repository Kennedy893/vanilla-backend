from datetime import datetime, time, timezone

from app.services.lot_rules import ensure_lot_not_archived
from app.services.lots_service import generate_event_code
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

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
from app.schemas.transfer import LotStateError, PendingTransferItem, TransferCreate, TransferReceive, TransferReject

TRANSFER_ROLES = {MemberRole.OPERATOR, MemberRole.MANAGER, MemberRole.OWNER}
RECEPTION_ROLES = {MemberRole.OPERATOR, MemberRole.MANAGER, MemberRole.OWNER}

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
    ensure_lot_not_archived(lot)
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

def _load_open_transfer(
    db: Session,
    transfer_id: int,
    organization: Organization,
    role: MemberRole,
) -> tuple[Transfer, TraceabilityEvent, Lot]:
    """Load (and lock) a transfer waiting for reception, with its event and its lot.
 
    Shared by validate_transfer and reject_transfer: same access rules for both.
    """
    if role not in RECEPTION_ROLES:
        raise PermissionError("Votre rôle ne permet pas de réceptionner un transfert.")
 
    # Seule l'organisation DESTINATAIRE voit ce transfert. Pour les autres (y compris
    # l'expéditeur), c'est « introuvable ». La ligne est verrouillée : deux décisions
    # simultanées sur le même transfert sont impossibles.
    transfer = db.scalar(
        select(Transfer)
        .where(Transfer.id == transfer_id, Transfer.to_organization_id == organization.id)
        .with_for_update()
    )
    if transfer is None:
        raise LookupError("Transfert introuvable.")
    if transfer.status != TransferStatus.DISPATCHED:
        raise LotStateError("Ce transfert n'est pas en attente de réception.")
 
    event = db.get(TraceabilityEvent, transfer.event_id)
 
    # Le lot transféré, retrouvé via event_lots
    lot = db.scalar(
        select(Lot)
        .join(EventLot, EventLot.lot_id == Lot.id)
        .where(
            EventLot.event_id == transfer.event_id,
            EventLot.role == EventLotRole.TRANSFERRED,
        )
        .with_for_update()
    )
    # Garde-fou : un transfert ouvert doit correspondre à un lot « in_transfer »
    # toujours détenu par l'expéditeur. Sinon les données sont incohérentes : on ne devine pas.
    if (
        event is None
        or lot is None
        or lot.status != LotStatus.IN_TRANSFER
        or lot.holder_id != transfer.from_organization_id
    ):
        raise LotStateError("Ce transfert est dans un état incohérent.")
 
    return transfer, event, lot
 
def validate_transfer(
    db: Session,
    transfer_id: int,
    data: TransferReceive,
    user: User,
    organization: Organization,
    role: MemberRole,
) -> Transfer:
    """Confirm the reception of a transfer: the lot changes holder.
 
    Raises:
        PermissionError: the role cannot receive transfers (-> 403).
        LookupError: transfer not found, or not addressed to this organization (-> 404).
        LotStateError: the transfer is not waiting for reception (-> 409).
        ValueError: reception date before the dispatch date (-> 422).
    """
    transfer, event, lot = _load_open_transfer(db, transfer_id, organization, role)
 
    receipt_at = datetime.combine(data.receipt_date, time.min)
    if transfer.dispatch_date is not None and receipt_at < transfer.dispatch_date:
        raise ValueError("La date de réception ne peut pas précéder l'expédition.")
 
    try:
        transfer.status = TransferStatus.RECEIVED
        transfer.receipt_date = receipt_at
 
        event.status = EventStatus.VALIDATED
        event.validated_by_id = user.id
        event.validated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # Le lieu actuel d'un lot = le lieu de son dernier événement validé.
        # Le transfert est maintenant terminé : le lot est à destination.
        event.location_id = transfer.destination_location_id
 
        lot.holder_id = transfer.to_organization_id  # le changement de détenteur
        lot.status = LotStatus.AVAILABLE
        db.commit()
    except Exception:
        db.rollback()
        raise
 
    db.refresh(transfer)
    return transfer
 
 
def reject_transfer(
    db: Session,
    transfer_id: int,
    data: TransferReject,
    user: User,
    organization: Organization,
    role: MemberRole,
) -> Transfer:
    """Refuse the reception: the lot goes back to AVAILABLE, still held by the sender.
 
    Raises:
        PermissionError: the role cannot receive transfers (-> 403).
        LookupError: transfer not found, or not addressed to this organization (-> 404).
        LotStateError: the transfer is not waiting for reception (-> 409).
    """
    transfer, event, lot = _load_open_transfer(db, transfer_id, organization, role)
 
    try:
        transfer.status = TransferStatus.REJECTED
 
        event.status = EventStatus.REJECTED
        # Pas de colonne dédiée : validated_by_id / validated_at servent ici à garder
        # QUI a refusé et QUAND (la décision), pour que l'historique l'affiche.
        event.validated_by_id = user.id
        event.validated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # Le motif s'ajoute aux notes de l'expéditeur sans les écraser
        reason_line = f"Motif du refus : {data.reason}"
        event.description = f"{event.description}\n{reason_line}" if event.description else reason_line
 
        lot.status = LotStatus.AVAILABLE  # le détenteur n'a pas changé : l'expéditeur
        db.commit()
    except Exception:
        db.rollback()
        raise
 
    db.refresh(transfer)
    return transfer

def get_pending_transfers(
    db: Session,
    organization: Organization,
) -> list[PendingTransferItem]:
    """Return the transfers waiting for reception BY `organization` (incoming, status
    'dispatched'), oldest dispatch first: the queue is processed in arrival order.
 
    No role check: every member can read the list. Acting on a transfer
    (validate_transfer / reject_transfer) requires operator or higher.
    """
    # Une table jointe plusieurs fois => alias : organisation expéditrice, deux lieux, expéditeur
    from_org = aliased(Organization)
    origin = aliased(Location)
    destination = aliased(Location)
    sender = aliased(User)
 
    stmt = (
        select(
            Transfer,
            TraceabilityEvent,
            Lot,
            from_org.name,
            origin.name,
            destination.name,
            sender.username,
        )
        .select_from(Transfer)
        .join(TraceabilityEvent, TraceabilityEvent.id == Transfer.event_id)
        # le lot transféré, via event_lots
        .join(
            EventLot,
            (EventLot.event_id == Transfer.event_id) & (EventLot.role == EventLotRole.TRANSFERRED),
        )
        .join(Lot, Lot.id == EventLot.lot_id)
        .join(from_org, from_org.id == Transfer.from_organization_id)
        .join(origin, origin.id == Transfer.origin_location_id)
        .join(destination, destination.id == Transfer.destination_location_id)
        .join(sender, sender.id == TraceabilityEvent.recorded_by_id)
        # l'organisation active est la DESTINATAIRE, jamais un paramètre du client
        .where(
            Transfer.to_organization_id == organization.id,
            Transfer.status == TransferStatus.DISPATCHED,
        )
        .order_by(Transfer.dispatch_date.asc(), Transfer.id.asc())
    )
 
    return [
        PendingTransferItem(
            transfer_id=transfer.id,
            event_code=event.event_code,
            dispatch_date=transfer.dispatch_date,
            from_organization_id=transfer.from_organization_id,
            from_organization_name=from_name,
            sent_by=sent_by,
            origin_location_name=origin_name,
            destination_location_name=destination_name,
            notes=event.description,
            lot_id=lot.id,
            lot_code=lot.lot_code,
            quantity_kg=lot.quantity_kg,
            product_state=lot.product_state,
        )
        for transfer, event, lot, from_name, origin_name, destination_name, sent_by
        in db.execute(stmt).all()
    ]