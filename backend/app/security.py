"""Authentication (JWT bearer tokens) and role-based authorisation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .domain.enums import Role
from .domain.exceptions import AuthenticationRequiredError, UnauthorizedOperationError
from .models import User

bearer = HTTPBearer(auto_error=False)


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id), "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiry_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationRequiredError("Session expired, please log in again") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationRequiredError("Invalid authentication token") from exc


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise AuthenticationRequiredError()
    data = decode_token(creds.credentials)
    user = db.get(User, int(data["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationRequiredError("Account disabled or removed")
    return user


def require_roles(*roles: Role) -> Callable:
    allowed = {r.value for r in roles}

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise UnauthorizedOperationError(
                f"This action requires role: {', '.join(sorted(allowed))}")
        return user
    return dep


def require_permission(permission: str) -> Callable:
    def dep(user: User = Depends(current_user)) -> User:
        if not user.can(permission):
            raise UnauthorizedOperationError(f"Missing permission '{permission}'")
        return user
    return dep
