from datetime import datetime, timezone

from app.services.lot_rules import is_lot_archived
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lot, LotStatus, MemberRole, Organization, User
from app.schemas.lot import LotArchive
from app.services.exceptions import LotStateError

ARCHIVE_ROLES = {MemberRole.MANAGER, MemberRole.OWNER}
# Désarchiver annule une décision finale : réservé au propriétaire de l'organisation
UNARCHIVE_ROLES = {MemberRole.OWNER}

# Seuls ces statuts peuvent être archivés manuellement
ARCHIVABLE_STATUSES = {LotStatus.AVAILABLE, LotStatus.BLOCKED}

# Message précis selon le statut, pour que l'utilisateur sache quoi faire
REFUSAL_MESSAGES = {
    LotStatus.CREATED: "Un lot en attente de validation ne peut pas être archivé.",
    LotStatus.IN_TRANSFER: (
        "Un lot en transfert ne peut pas être archivé : "
        "le transfert doit d'abord être reçu ou refusé."
    ),
    LotStatus.PROCESSING: "Un lot en transformation ne peut pas être archivé manuellement.",
    LotStatus.EXPORTED: "Un lot exporté ne peut pas être archivé.",
    LotStatus.ARCHIVED: "Ce lot est déjà archivé.",
}


def archive_lot(
    db: Session,
    lot_id: int,
    data: LotArchive,
    user: User,
    organization: Organization,
    role: MemberRole,
) -> Lot:
    """Archive a lot: it leaves circulation but is never deleted (final state).

    Who, when and why are stored on the lot (archived_by_id, archived_at, archive_reason).
    Nothing else changes: quantity, holder, farm, events and lineage stay as they are.

    Raises:
        PermissionError: the role cannot archive (-> 403).
        LookupError: the lot does not exist or is not held by the organization (-> 404).
        LotStateError: the lot status does not allow archiving (-> 409).
    """
    if role not in ARCHIVE_ROLES:
        raise PermissionError("Votre rôle ne permet pas d'archiver un lot.")

    # Verrou sur la ligne : deux archivages simultanés, ou un archivage pendant
    # un transfert du même lot, ne peuvent pas se croiser.
    lot = db.scalar(
        select(Lot)
        .where(Lot.id == lot_id, Lot.holder_id == organization.id)
        .with_for_update()
    )
    if lot is None:
        raise LookupError("Lot introuvable.")

    last_status = lot.status  # pour l'archived_from_status

    if lot.status not in ARCHIVABLE_STATUSES:
        raise LotStateError(
            REFUSAL_MESSAGES.get(lot.status, "Ce lot ne peut pas être archivé dans son état actuel.")
        )

    try:
        lot.status = LotStatus.ARCHIVED
        lot.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        lot.archived_by_id = user.id
        lot.archive_reason = data.reason
        lot.archived_from_status = last_status.value
        db.commit()  # updated_at est mis à jour automatiquement
    except Exception:
        db.rollback()
        raise

    db.refresh(lot)
    return lot

def _status_to_restore(lot: Lot) -> LotStatus:
    """Statut à rendre au lot : celui d'avant l'archivage.
 
    Par prudence, tout cas douteux (lot archivé avant l'existence de cette colonne, valeur
    inconnue) donne « blocked » : on ne remet jamais en circulation un lot qui était bloqué
    (par exemple après un contrôle qualité négatif) sans que quelqu'un le décide.
    """
    try:
        previous = LotStatus(lot.archived_from_status)
    except ValueError:  # None ou valeur inconnue
        return LotStatus.BLOCKED
    return previous if previous in ARCHIVABLE_STATUSES else LotStatus.BLOCKED
 
 
def unarchive_lot(
    db: Session,
    lot_id: int,
    organization: Organization,
    role: MemberRole,
) -> Lot:
    """Unarchive a lot: it gets back the status it had before being archived.
 
    Warning: the archive information (who, when, why) is cleared, and nothing else keeps
    track of it. Keeping a history of archivings would need an audit table.
 
    Raises:
        PermissionError: the role cannot unarchive (-> 403).
        LookupError: the lot does not exist or is not held by the organization (-> 404).
        LotStateError: the lot is not archived (-> 409).
    """
    if role not in UNARCHIVE_ROLES:
        raise PermissionError("Seul le propriétaire de l'organisation peut désarchiver un lot.")
 
    lot = db.scalar(
        select(Lot)
        .where(Lot.id == lot_id, Lot.holder_id == organization.id)
        .with_for_update()
    )
    if lot is None:
        raise LookupError("Lot introuvable.")
 
    if not is_lot_archived(lot):
        raise LotStateError("Ce lot n'est pas archivé.")
 
    try:
        lot.status = _status_to_restore(lot)
        # Un lot actif n'a plus d'informations d'archivage (exigé par la contrainte CHECK)
        lot.archived_at = None
        lot.archived_by_id = None
        lot.archive_reason = None
        lot.archived_from_status = None
        db.commit()
    except Exception:
        db.rollback()
        raise
 
    db.refresh(lot)
    return lot