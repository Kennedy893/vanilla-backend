from datetime import datetime, time, timezone, timedelta

from sqlalchemy import text, func, select
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
from app.schemas.lot import FarmSummary, LotCreate, LotListFilters, LotListFilters, LotListItem, LotListResponse

# Règles de gestion (à ajuster ici, à un seul endroit)
HARVEST_ORGANIZATION_TYPES = {OrganizationType.PRODUCER, OrganizationType.COOPERATIVE}
WRITE_ROLES = {MemberRole.OPERATOR, MemberRole.MANAGER, MemberRole.OWNER}
# AUTO_VALIDATE_ROLES = {MemberRole.MANAGER, MemberRole.OWNER}
AUTO_VALIDATE_ROLES: set[MemberRole] = set()


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

# Date de récolte d'un lot = date de son événement de récolte (lien via event_lots).
# min() + group by => une seule ligne par lot, même si l'historique contient un doublon.
# Remarque : les événements annulés/rejetés ne sont pas exclus ici ; à affiner si besoin.
_HARVEST = (
    select(
        EventLot.lot_id.label("lot_id"),
        func.min(TraceabilityEvent.event_date).label("harvest_date"),
    )
    .join(TraceabilityEvent, TraceabilityEvent.id == EventLot.event_id)
    .where(
        TraceabilityEvent.event_type == EventType.HARVEST,
        EventLot.role == EventLotRole.OUTPUT,
    )
    .group_by(EventLot.lot_id)
    .subquery("harvest")
)
 
# Liste blanche des tris autorisés (on n'injecte jamais un nom de colonne venant du client)
_SORT_COLUMNS = {
    "harvest_date": _HARVEST.c.harvest_date,
    "created_at": Lot.created_at,
    "lot_code": Lot.lot_code,
    "quantity_kg": Lot.quantity_kg,
}
 
 
def _select_from_lots(*columns):
    """SELECT <columns> FROM lots JOIN farms LEFT JOIN harvest."""
    return (
        select(*columns)
        .select_from(Lot)
        .join(Farm, Farm.id == Lot.farm_id)
        .outerjoin(_HARVEST, _HARVEST.c.lot_id == Lot.id)
    )
 
 
def _escape_like(value: str) -> str:
    """Neutralise % et _ pour qu'une recherche utilisateur soit littérale."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
 
 
def _base_conditions(organization: Organization, f: LotListFilters) -> list:
    """Conditions communes, SANS le statut (utile pour les compteurs des onglets)."""
    # holder_id vient de l'organisation active validée côté serveur, jamais du client
    conditions = [Lot.holder_id == organization.id]
    if f.product_state:
        conditions.append(Lot.product_state == f.product_state)
    if f.farm_id:
        conditions.append(Lot.farm_id == f.farm_id)
    if f.q:
        conditions.append(Lot.lot_code.ilike(f"%{_escape_like(f.q)}%", escape="\\"))
    if f.harvest_from:
        conditions.append(_HARVEST.c.harvest_date >= datetime.combine(f.harvest_from, time.min))
    if f.harvest_to:  # bornes inclusives : on va jusqu'au lendemain 00:00 exclu
        conditions.append(
            _HARVEST.c.harvest_date < datetime.combine(f.harvest_to + timedelta(days=1), time.min)
        )
    return conditions
 
 
def get_lots(
    db: Session,
    organization: Organization,
    filters: LotListFilters,
) -> LotListResponse:
    """Return the lots held by `organization`, filtered, sorted and paginated.
 
    Args:
        db: The database session.
        organization: The active organization (already validated by get_org_context).
        filters: Validated query parameters (filters, sort, pagination).
 
    Returns:
        A LotListResponse: the page of items, the total count and per-status counts.
    """
    base = _base_conditions(organization, filters)
    with_status = base + ([Lot.status == filters.status] if filters.status else [])
 
    # 1) Total pour la pagination (tous filtres)
    total = db.scalar(_select_from_lots(func.count(Lot.id)).where(*with_status)) or 0
 
    # 2) Compteurs par statut (tous filtres sauf le statut), zéros inclus
    status_counts = {status.value: 0 for status in LotStatus}
    rows = db.execute(
        _select_from_lots(Lot.status, func.count(Lot.id)).where(*base).group_by(Lot.status)
    ).all()
    for status, count in rows:
        if status is not None:
            status_counts[status.value] = count
 
    # 3) La page demandée. Lot.id en départage : ordre stable entre deux pages
    sort_column = _SORT_COLUMNS[filters.sort]
    primary_order = (
        sort_column.desc().nulls_last()
        if filters.order == "desc"
        else sort_column.asc().nulls_last()
    )
    page = db.execute(
        _select_from_lots(Lot, Farm, _HARVEST.c.harvest_date)
        .where(*with_status)
        .order_by(primary_order, Lot.id.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    ).all()
 
    items = [
        LotListItem(
            id=lot.id,
            lot_code=lot.lot_code,
            product_state=lot.product_state,
            quantity_kg=lot.quantity_kg,
            status=lot.status,
            farm=FarmSummary.model_validate(farm),
            harvest_date=harvest_date,
            created_at=lot.created_at,
        )
        for lot, farm, harvest_date in page
    ]
 
    return LotListResponse(
        items=items,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
        status_counts=status_counts,
    )


VALIDATE_ROLES = {MemberRole.MANAGER, MemberRole.OWNER}

class LotStateError(Exception):
    """Le lot n'est pas dans un état qui permet cette action (-> 409)."""

def validate_lot(
    db: Session,
    lot_id: int,
    user: User,
    organization: Organization,
    role: MemberRole,
) -> Lot:
    """Validate a lot's harvest: event PENDING -> VALIDATED and lot CREATED -> AVAILABLE.
 
    Both changes happen in one transaction: both succeed or none does.
 
    Raises:
        PermissionError: the role cannot validate (-> 403).
        LookupError: the lot does not exist or is not held by the organization (-> 404).
        LotStateError: the lot is not waiting for validation (-> 409).
    """
    if role not in VALIDATE_ROLES:
        raise PermissionError("Votre rôle ne permet pas de valider un lot.")
 
    # NB : la ligne du lot est verrouillée jusqu'à la fin de la transaction.
    # Si deux managers valident en même temps, le second attend, puis voit le statut
    # déjà passé à AVAILABLE et reçoit l'erreur « pas en attente ».
    lot = db.scalar(
        select(Lot)
        .where(Lot.id == lot_id, Lot.holder_id == organization.id)
        .with_for_update()
    )
    if lot is None:
        raise LookupError("Lot introuvable.")
 
    if lot.status != LotStatus.CREATED:
        raise LotStateError("Ce lot n'est pas en attente de validation.")
 
    # L'événement de récolte en attente de ce lot (via event_lots)
    event = db.scalar(
        select(TraceabilityEvent)
        .join(EventLot, EventLot.event_id == TraceabilityEvent.id)
        .where(
            EventLot.lot_id == lot.id,
            EventLot.role == EventLotRole.OUTPUT,
            TraceabilityEvent.event_type == EventType.HARVEST,
            TraceabilityEvent.status == EventStatus.PENDING,
        )
    )
    if event is None:
        # Lot « created » sans récolte en attente : données incohérentes, on ne devine pas
        raise LotStateError("Aucune récolte en attente de validation pour ce lot.")
 
    try:
        event.status = EventStatus.VALIDATED
        event.validated_by_id = user.id
        event.validated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        lot.status = LotStatus.AVAILABLE  # updated_at est mis à jour automatiquement
        db.commit()
    except Exception:
        db.rollback()
        raise
 
    db.refresh(lot)
    return lot