from app.schemas.lot import LotHistoryEvent, QualityCheckSummary
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models import (
    EventLot,
    Location,
    Lot,
    Organization,
    QualityCheck,
    TraceabilityEvent,
    User,
)


def get_lots_historical(
    db: Session,
    organization: Organization,
    lot_id: int,
) -> list[LotHistoryEvent]:
    """Return the chronological history (oldest first) of one lot.

    Reading order: event_lots -> traceability_events -> locations / users x2 /
    organizations -> quality_checks (LEFT JOIN, only filled for quality_check events).

    Raises:
        LookupError: the lot does not exist or is not held by `organization` (-> 404).
    """
    # Garde d'accès : même erreur si le lot n'existe pas ou appartient à un autre détenteur
    lot_exists = db.scalar(
        select(Lot.id).where(Lot.id == lot_id, Lot.holder_id == organization.id)
    )
    if lot_exists is None:
        raise LookupError("Lot introuvable.")

    # La table users est jointe deux fois (auteur, validateur) + une fois pour le contrôleur
    recorder = aliased(User)
    validator = aliased(User)
    checker = aliased(User)

    stmt = (
        select(
            EventLot,
            TraceabilityEvent,
            Location.name,
            Organization.name,
            recorder.username,
            validator.username,
            QualityCheck,
            checker.username,
        )
        # 1) event_lots : quels événements concernent ce lot ?
        .select_from(EventLot)
        # 2) traceability_events : le détail de chaque événement
        .join(TraceabilityEvent, TraceabilityEvent.id == EventLot.event_id)
        # 3) lieu, auteur, validateur (peut être vide), organisation (peut être vide)
        .join(Location, Location.id == TraceabilityEvent.location_id)
        .join(recorder, recorder.id == TraceabilityEvent.recorded_by_id)
        .outerjoin(validator, validator.id == TraceabilityEvent.validated_by_id)
        .outerjoin(Organization, Organization.id == TraceabilityEvent.organization_id)
        # 4) quality_checks : seulement pour les événements de contrôle ; on exige aussi
        #    le même lot, au cas où un événement concernerait plusieurs lots
        .outerjoin(
            QualityCheck,
            (QualityCheck.event_id == TraceabilityEvent.id) & (QualityCheck.lot_id == lot_id),
        )
        .outerjoin(checker, checker.id == QualityCheck.checked_by_id)
        .where(EventLot.lot_id == lot_id)
        # 5) ordre chronologique croissant, id en départage
        .order_by(TraceabilityEvent.event_date.asc(), TraceabilityEvent.id.asc())
    )

    history = []
    for (
        event_lot,
        event,
        location_name,
        organization_name,
        recorded_by,
        validated_by,
        check,
        checked_by,
    ) in db.execute(stmt).all():
        history.append(
            LotHistoryEvent(
                event_id=event.id,
                event_code=event.event_code,
                event_type=event.event_type,
                event_date=event.event_date,
                status=event.status,
                description=event.description,
                location_name=location_name,
                organization_name=organization_name,
                recorded_by=recorded_by,
                validated_by=validated_by,
                validated_at=event.validated_at,
                role=event_lot.role,
                quantity_kg=event_lot.quantity_kg,
                quality_check=(
                    QualityCheckSummary(
                        result=check.result,
                        grade=check.grade,
                        moisture_percentage=check.moisture_percentage,
                        comments=check.comments,
                        checked_by=checked_by,
                    )
                    if check is not None
                    else None
                ),
            )
        )
    return history