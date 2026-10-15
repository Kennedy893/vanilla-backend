from app.core.token import ALGORITHM, SECRET_KEY
from app.database import get_db
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.core.security import verify_password

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

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

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency FastAPI : récupère l'utilisateur depuis le token JWT."""
    credentials_exception = HTTPException(
        status_code=401,
        detail="Identifiants invalides",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get(User, int(user_id))
    if user is None:
        raise credentials_exception
    return user