class LotStateError(Exception):
    """Le lot n'est pas dans un état qui permet cette action (-> 409)."""

class ConflictError(Exception):
    """L'action est en conflit avec des données existantes : doublon, élément utilisé (-> 409)."""