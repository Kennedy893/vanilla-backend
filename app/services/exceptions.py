class LotStateError(Exception):
    """Le lot n'est pas dans un état qui permet cette action (-> 409)."""