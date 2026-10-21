from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    Farm,
    Location,
    Lot,
    MemberRole,
    Organization,
    OrganizationType,
    TraceabilityEvent,
    Transfer,
)
from app.schemas.farm import FarmCreate, FarmListItem, FarmListResponse, FarmUpdate
from app.services.exceptions import ConflictError

# Ce sont des données de référence, pas de la saisie courante
FARM_WRITE_ROLES = {MemberRole.MANAGER, MemberRole.OWNER}
HARVEST_ORGANIZATION_TYPES = {OrganizationType.PRODUCER, OrganizationType.COOPERATIVE}

# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
def get_farms_by_organization(db: Session, organization: Organization):
    """Liste simple des exploitations de l'organisation (alimente la liste déroulante
    de création d'un lot). Inchangée, avec un tri par nom."""
    return (
        db.query(Farm)
        .filter(Farm.producer_organization_id == organization.id)
        .order_by(Farm.name, Farm.id)
        .all()
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_farms_list(
    db: Session,
    organization: Organization,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> FarmListResponse:
    """Liste paginée pour la page « Exploitations » : localité, coordonnées, nombre de lots.

    Tous les rôles peuvent lire. La recherche porte sur le nom et le code.
    """
    # Nombre de lots par exploitation (une seule requête, pas une par ligne)
    lots_per_farm = (
        select(Lot.farm_id.label("farm_id"), func.count(Lot.id).label("n"))
        .group_by(Lot.farm_id)
        .subquery()
    )

    conditions = [Farm.producer_organization_id == organization.id]
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        conditions.append(
            Farm.name.ilike(pattern, escape="\\") | Farm.farm_code.ilike(pattern, escape="\\")
        )

    total = db.scalar(select(func.count(Farm.id)).where(*conditions)) or 0

    rows = db.execute(
        select(Farm, Location, func.coalesce(lots_per_farm.c.n, 0))
        .join(Location, Location.id == Farm.location_id)
        .outerjoin(lots_per_farm, lots_per_farm.c.farm_id == Farm.id)
        .where(*conditions)
        .order_by(Farm.name, Farm.id)
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        FarmListItem(
            id=farm.id,
            farm_code=farm.farm_code,
            name=farm.name,
            area_hectares=farm.area_hectares,
            location_name=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
            lots_count=lots_count,
            created_at=farm.created_at,
        )
        for farm, location, lots_count in rows
    ]
    return FarmListResponse(items=items, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------
def _next_sequence_value(db: Session, sequence_name: str) -> int:
    """Prochaine valeur d'une séquence PostgreSQL (le nom est une constante, jamais une saisie)."""
    return db.scalar(text(f"SELECT nextval('{sequence_name}')"))


def generate_farm_code(db: Session) -> str:
    """FARM-0001, FARM-0002, ... (séquence : pas de doublon même en cas de requêtes simultanées)."""
    return f"FARM-{_next_sequence_value(db, 'farm_code_seq'):04d}"


def _check_write_access(organization: Organization, role: MemberRole) -> None:
    if role not in FARM_WRITE_ROLES:
        raise PermissionError("Votre rôle ne permet pas de gérer les exploitations.")
    if organization.organization_type not in HARVEST_ORGANIZATION_TYPES:
        raise PermissionError("Ce type d'organisation n'a pas d'exploitations.")


def _get_own_farm(db: Session, farm_id: int, organization: Organization) -> Farm:
    """L'exploitation de l'organisation active, verrouillée ; 404 pour celles des autres."""
    farm = db.scalar(
        select(Farm)
        .where(Farm.id == farm_id, Farm.producer_organization_id == organization.id)
        .with_for_update()
    )
    if farm is None:
        raise LookupError("Exploitation introuvable.")
    return farm


def _name_taken(
    db: Session, organization: Organization, name: str, exclude_farm_id: int | None = None
) -> bool:
    """Le nom est unique dans l'organisation, sans tenir compte des majuscules."""
    stmt = select(Farm.id).where(
        Farm.producer_organization_id == organization.id,
        func.lower(Farm.name) == name.lower(),
    )
    if exclude_farm_id is not None:
        stmt = stmt.where(Farm.id != exclude_farm_id)
    return db.scalar(stmt.limit(1)) is not None


def create_farm(
    db: Session,
    data: FarmCreate,
    organization: Organization,
    role: MemberRole,
) -> Farm:
    """Create a farm together with its own location, in one transaction.

    The code is generated by the server; the owner is the active organization.

    Raises:
        PermissionError: role or organization type not allowed (-> 403).
        ConflictError: another farm of the organization already has this name (-> 409).
    """
    _check_write_access(organization, role)
    if _name_taken(db, organization, data.name):
        raise ConflictError("Une exploitation porte déjà ce nom.")

    try:
        # Chaque exploitation a son propre lieu : la modifier ne touche aucun lieu partagé
        location = Location(
            name=data.location_name,
            location_type="farm",
            latitude=data.latitude,
            longitude=data.longitude,
        )
        db.add(location)
        db.flush()

        farm = Farm(
            farm_code=generate_farm_code(db),
            name=data.name,
            area_hectares=data.area_hectares,
            producer_organization_id=organization.id,
            location_id=location.id,
        )
        db.add(farm)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(farm)
    return farm


def update_farm(
    db: Session,
    farm_id: int,
    data: FarmUpdate,
    organization: Organization,
    role: MemberRole,
) -> Farm:
    """Update name, area and/or location of a farm. Only the fields sent are changed.

    The code and the owner organization never change.

    Raises:
        PermissionError: role or organization type not allowed (-> 403).
        LookupError: farm not found in this organization (-> 404).
        ConflictError: the new name is already used by another farm (-> 409).
    """
    _check_write_access(organization, role)
    farm = _get_own_farm(db, farm_id, organization)
    provided = data.model_fields_set

    try:
        if "name" in provided and data.name != farm.name:
            if _name_taken(db, organization, data.name, exclude_farm_id=farm.id):
                raise ConflictError("Une exploitation porte déjà ce nom.")
            farm.name = data.name

        if "area_hectares" in provided:
            farm.area_hectares = data.area_hectares

        if provided & {"location_name", "latitude", "longitude"}:
            location = db.get(Location, farm.location_id)
            name = data.location_name if "location_name" in provided else location.name
            latitude = data.latitude if "latitude" in provided else location.latitude
            longitude = data.longitude if "longitude" in provided else location.longitude

            shared = db.scalar(
                select(Farm.id)
                .where(Farm.location_id == location.id, Farm.id != farm.id)
                .limit(1)
            )
            if shared is not None:
                # Lieu partagé avec une autre exploitation (anciennes données) : on ne
                # le modifie pas, on en crée un propre à cette exploitation.
                location = Location(location_type="farm")
                db.add(location)

            location.name = name
            location.latitude = latitude
            location.longitude = longitude
            db.flush()
            farm.location_id = location.id

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(farm)
    return farm


def _location_in_use(db: Session, location_id: int) -> bool:
    """Un lieu est-il encore référencé (autre exploitation, événement, transfert) ?"""
    queries = [
        select(Farm.id).where(Farm.location_id == location_id),
        select(TraceabilityEvent.id).where(TraceabilityEvent.location_id == location_id),
        select(Transfer.id).where(
            (Transfer.origin_location_id == location_id)
            | (Transfer.destination_location_id == location_id)
        ),
    ]
    return any(db.scalar(query.limit(1)) is not None for query in queries)


def delete_farm(
    db: Session,
    farm_id: int,
    organization: Organization,
    role: MemberRole,
) -> None:
    """Delete a farm that has no lot (archived lots count too).

    Its location is deleted as well, unless something else still refers to it.

    Raises:
        PermissionError: role or organization type not allowed (-> 403).
        LookupError: farm not found in this organization (-> 404).
        ConflictError: lots come from this farm (-> 409).
    """
    _check_write_access(organization, role)
    farm = _get_own_farm(db, farm_id, organization)

    lots_count = db.scalar(select(func.count(Lot.id)).where(Lot.farm_id == farm.id)) or 0
    if lots_count > 0:
        raise ConflictError(
            f"Cette exploitation est utilisée par {lots_count} lot(s) : elle ne peut pas être supprimée."
        )

    location_id = farm.location_id
    try:
        db.delete(farm)
        db.flush()
        if not _location_in_use(db, location_id):
            db.delete(db.get(Location, location_id))
        db.commit()
    except Exception:
        db.rollback()
        raise