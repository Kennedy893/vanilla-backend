from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MemberRole, Organization, OrganizationMember, User
from app.services.auth_service import get_current_user


@dataclass
class OrgContext:
    """Qui agit (user), pour quelle organisation, avec quel rôle."""

    user: User
    organization: Organization
    role: MemberRole


def get_org_context(
    x_organization_id: int = Header(..., description="Organisation active"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrgContext:
    """Résout l'organisation active ET vérifie que l'utilisateur en est membre.

    Le client indique l'organisation voulue (en-tête X-Organization-Id) ;
    le serveur ne lui fait jamais confiance sans vérifier l'appartenance.
    """
    membership = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == x_organization_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Vous n'êtes pas membre de cette organisation.")

    organization = db.get(Organization, x_organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=403, detail="Organisation inactive ou introuvable.")

    return OrgContext(user=user, organization=organization, role=membership.role)