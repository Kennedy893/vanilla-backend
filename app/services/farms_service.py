from sqlalchemy.orm import Session
from app.models import Farm, Organization


def get_farms_by_organization(db: Session, organization: Organization):
    """
    Récupère la liste des fermes.

    Returns:
        Une liste de fermes.
    """
    farms = db.query(Farm).filter(Farm.producer_organization_id == organization.id).all()
    return farms