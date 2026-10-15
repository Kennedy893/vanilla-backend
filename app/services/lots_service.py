from datetime import datetime, time, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    EventLot,
    EventLotRole,
    EventStatus,
    EventType,
    Farm,
    Lot,
    LotStatus,
    LotType,
    MemberRole,
    Organization,
    OrganizationType,
    ProductState,
    TraceabilityEvent,
    User,
)
from app.schemas.lot import LotCreate

# Règles de gestion (à ajuster ici, à un seul endroit)
HARVEST_ORGANIZATION_TYPES = {OrganizationType.PRODUCER, OrganizationType.COOPERATIVE}
WRITE_ROLES = {MemberRole.OPERATOR, MemberRole.MANAGER, MemberRole.OWNER}
AUTO_VALIDATE_ROLES = {MemberRole.MANAGER, MemberRole.OWNER}


def _next_sequence_value(db: Session, sequence_name: str) -> int:
    """Next value of a PostgreSQL sequence (atomic, safe under concurrency).

    `sequence_name` is always a constant defined in this module, never user input.
    """
    return db.scalar(text(f"SELECT nextval('{sequence_name}')"))


def generate_lot_code(db: Session) -> str:
    """Generate a unique lot code from a database sequence.

    Format: LOT-0001, LOT-0002, ... (grows to LOT-10000 etc. when needed).
    Unlike 'last id + 1', two simultaneous requests can never get the same number.
    Gaps are possible (a rolled-back creation consumes a number) and harmless.
    """
    return f"LOT-{_next_sequence_value(db, 'lot_code_seq'):04d}"


def generate_event_code(db: Session) -> str:
    """Generate a unique traceability event code: EVT-000001, EVT-000002, ..."""
    return f"EVT-{_next_sequence_value(db, 'event_code_seq'):06d}"


def create_lot(
    db: Session,
    data: LotCreate,
    user: User,
    organization: Organization,
    role: MemberRole,
) -> Lot:
    """Create a harvest lot together with its first traceability event.

    Args:
        db: The database session.
        data: Validated input (farm, quantity, harvest date, notes).
        user: The authenticated user (becomes the event's author).
        organization: The active organization (becomes the lot's holder).
        role: The user's role inside that organization.

    Returns:
        The created Lot (serialize it with LotRead).

    Raises:
        PermissionError: role or organization type not allowed to create lots (-> 403).
        LookupError: farm not found or not owned by the organization (-> 404).
    """
    # 1) Règles d'autorisation
    if role not in WRITE_ROLES:
        raise PermissionError("Votre rôle ne permet pas de créer un lot.")
    if organization.organization_type not in HARVEST_ORGANIZATION_TYPES:
        raise PermissionError("Ce type d'organisation ne peut pas enregistrer de récolte.")

    # 2) L'exploitation doit exister ET appartenir à l'organisation active.
    #    Même erreur dans les deux cas : on ne révèle pas l'existence des fermes des autres.
    farm = db.get(Farm, data.farm_id)
    if farm is None or farm.producer_organization_id != organization.id:
        raise LookupError("Exploitation introuvable.")

    # 3) Validation automatique si l'auteur est manager/owner, sinon en attente
    auto_validated = role in AUTO_VALIDATE_ROLES
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 4) Tout ou rien : lot + événement + liaison dans UNE transaction
    try:
        lot = Lot(
            lot_code=generate_lot_code(db),
            lot_type=LotType.HARVEST,
            product_state=ProductState.FRESH,
            quantity_kg=data.quantity_kg,
            status=LotStatus.AVAILABLE if auto_validated else LotStatus.CREATED,
            farm_id=farm.id,
            holder_id=organization.id,
            # created_at : rempli par la base (DEFAULT NOW())
            # updated_at : reste vide à la création, mis à jour lors des modifications
        )
        db.add(lot)
        db.flush()  # obtient lot.id sans valider la transaction

        event = TraceabilityEvent(
            event_code=generate_event_code(db),
            event_type=EventType.HARVEST,
            event_date=datetime.combine(data.harvest_date, time.min),
            description=data.notes,
            status=EventStatus.VALIDATED if auto_validated else EventStatus.PENDING,
            validated_at=now if auto_validated else None,
            validated_by_id=user.id if auto_validated else None,
            recorded_by_id=user.id,
            location_id=farm.location_id,
            organization_id=organization.id,
        )
        db.add(event)
        db.flush()

        db.add(
            EventLot(
                event_id=event.id,
                lot_id=lot.id,
                role=EventLotRole.OUTPUT,
                quantity_kg=data.quantity_kg,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(lot)
    return lot