from app.services.locations_service import get_all_locations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.location import LocationRead

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.get("", response_model=list[LocationRead])
def list_all_locations(
    db: Session = Depends(get_db),
):
    return get_all_locations(db=db)