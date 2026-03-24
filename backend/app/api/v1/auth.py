from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from passlib.hash import argon2
from sqlalchemy import func, select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.models.user import User
from app.schemas.auth import LoginRequest, SetupRequest, TokenResponse, UserResponse

router = APIRouter()


def create_token(user_id: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.secret_key,
        algorithm="HS256",
    )


def create_tokens(user_id: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_token(
            user_id, timedelta(minutes=settings.access_token_expire_minutes)
        ),
        refresh_token=create_token(
            user_id, timedelta(days=settings.refresh_token_expire_days)
        ),
    )


@router.post("/setup", response_model=TokenResponse)
async def setup(request: SetupRequest, db: DbSession):
    """First-time user creation. Only works if no users exist yet."""
    result = await db.execute(select(func.count(User.id)))
    count = result.scalar()
    if count and count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup already completed. Use /login instead.",
        )

    user = User(
        email=request.email,
        display_name=request.display_name,
        password_hash=argon2.hash(request.password),
        first_name=request.first_name,
        date_of_birth=request.date_of_birth,
    )
    db.add(user)
    await db.flush()

    return create_tokens(str(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: DbSession):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not argon2.verify(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return create_tokens(str(user.id))


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser):
    return UserResponse(id=str(user.id), email=user.email, display_name=user.display_name)
