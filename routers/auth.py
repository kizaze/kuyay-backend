from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import bcrypt
from datetime import datetime, timedelta
from database import get_db
import models
import schemas
import os

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

SECRET_KEY = os.getenv("SECRET_KEY", "kuyay-dev-secret-change-in-production")
ALGORITHM = "HS256"
TOKEN_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=TOKEN_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise exc
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise exc

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise exc
    return user


def require_owner(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != models.UserRole.dueno:
        raise HTTPException(status_code=403, detail="Se requiere rol de dueño")
    return current_user


@router.post("/register", response_model=schemas.Token)
def register(data: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="El correo ya está registrado")

    user = models.User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        phone=data.phone,
        address=data.address,
        role=models.UserRole.cliente,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return schemas.Token(
        access_token=create_token(user.id),
        token_type="bearer",
        user=schemas.UserResponse.model_validate(user),
    )


@router.post("/login", response_model=schemas.Token)
def login(data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    return schemas.Token(
        access_token=create_token(user.id),
        token_type="bearer",
        user=schemas.UserResponse.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserResponse)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
