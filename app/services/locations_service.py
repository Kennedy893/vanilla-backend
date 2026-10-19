from app.models import Location
from sqlalchemy.orm import Session

def get_all_locations(db: Session):
    """
    Récupère toutes les localisations.

    Returns:
        Une liste de localisations.
    """
    locations = db.query(Location).all()
    return locations