import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import AuthResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
limiter = Limiter(key_func=get_remote_address)


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


@router.post("/register", response_model=AuthResponse)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new student account and return an access token."""
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    user = User(
        name=body.name,
        email=body.email,
        phone=body.phone,
        college=body.college,
        password_hash=pwd_context.hash(body.password),
        role="student",
    )
    db.add(user)
    await db.flush()

    token = create_access_token(user.id, user.role)
    logger.info(f"New user registered: {user.email}")
    return AuthResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return an access token."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")

    token = create_access_token(user.id, user.role)
    logger.info(f"User logged in: {user.email}")
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(current_user: User = Depends(get_current_user)):
    """Issue a new token with a fresh expiry for a non-expired token."""
    token = create_access_token(current_user.id, current_user.role)
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    # Stateless logout — we use short-lived JWTs (15 min), so the client just drops the token.
    # No server-side blacklist is maintained. See README for assumptions.
    return {"message": "Logged out successfully"}
