from app.models import Lot, LotStatus

class LotStateError(Exception):
    """Le lot n'est pas dans un état qui permet cette action (-> 409)."""

def is_lot_archived(lot: Lot) -> bool:
    """True si le lot est archivé (le statut est la référence)."""
    return lot.status == LotStatus.ARCHIVED


def ensure_lot_not_archived(lot: Lot) -> None:
    """À appeler dans toute fonction qui modifie un lot, juste après l'avoir chargé :
    un lot archivé est en lecture seule.

    Raises:
        LotStateError: le lot est archivé (-> 409).
    """
    if is_lot_archived(lot):
        raise LotStateError("Ce lot est archivé : aucune action n'est possible.")