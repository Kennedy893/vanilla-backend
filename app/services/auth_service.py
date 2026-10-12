
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.core.security import verify_password


def authenticate_user(
    db: Session,
    username: str,
    password: str,
):
    # 1. Rechercher l'utilisateur dans la base de données
    user = db.scalar(
        select(User).where(User.username == username)
    )

    if user is None:
        return None

    # 2. Vérifier si le compte est actif
    if not user.is_active:
        return None

    # 3. Vérifier le mot de passe
    if not verify_password(password, user.password):
        return None

    # 4. Retourner l'utilisateur authentifié
    return user