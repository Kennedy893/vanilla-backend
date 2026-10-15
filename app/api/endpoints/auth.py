from app.core.token import create_access_token
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OrganizationMember
from app.schemas.auth import LoginRequest
from app.services.auth_service import authenticate_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = authenticate_user(
        db=db,
        username=data.username,
        password=data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user.id)
    membership = db.scalar(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.organization_id)
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "id": user.id,
        "organization_id": membership.organization_id if membership else None,
    }