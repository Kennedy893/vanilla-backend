from app.models import Location, Organization
from sqlalchemy.orm import Session

def get_all_organizations(db: Session):
    """
    Récupère toutes les organisations.

    Returns:
        Une liste de organisations.
    """
    organizations = db.query(Organization).all()
    return organizations