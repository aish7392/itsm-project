from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.enums import Role
from ..domain.exceptions import DuplicateEntityError, InvalidLoginError
from ..models import AuditLog, User
from ..repositories import UserRepository
from ..schemas import LoginIn, RegisterIn
from ..security import create_token, current_user
from ..services.factories import UserFactory
from .serializers import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Self-registration always creates an EMPLOYEE (privileged roles are admin-created)."""
    repo = UserRepository(db)
    if repo.by_email(body.email):
        raise DuplicateEntityError("An account with this email already exists")
    user = repo.add(UserFactory.create(Role.EMPLOYEE, body.name, body.email, body.password,
                                       department=body.department))
    db.add(AuditLog(user_id=user.id, action="USER_REGISTERED",
                    description=f"{user.email} registered"))
    return {"token": create_token(user), "user": user_out(user, detail=True)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = UserRepository(db).by_email(body.email)
    # same message for unknown email / wrong password (no user enumeration)
    if user is None or not user.verify_password(body.password):
        raise InvalidLoginError("Invalid email or password")
    if not user.is_active:
        raise InvalidLoginError("This account has been deactivated")
    db.add(AuditLog(user_id=user.id, action="USER_LOGIN", description=f"{user.email} logged in"))
    return {"token": create_token(user), "user": user_out(user, detail=True)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user, detail=True)
