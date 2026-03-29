from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from passlib.hash import argon2
from sqlalchemy import func, select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.auth.password_reset import (
    build_password_reset_url,
    consume_password_reset_token,
    issue_password_reset_token,
    revoke_other_password_reset_tokens,
    send_password_reset_instructions,
)
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SetupRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


def _validate_new_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )


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
    _validate_new_password(request.password)
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


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(request: ForgotPasswordRequest, db: DbSession):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if user is None:
        return ForgotPasswordResponse(
            message="If an account exists for that email, password reset instructions have been generated.",
            delivery="email",
        )

    raw_token, token_row = await issue_password_reset_token(db, user)
    reset_url = build_password_reset_url(raw_token)
    delivery = await send_password_reset_instructions(user, reset_url)
    token_row.delivery = delivery.delivery
    token_row.destination = user.email

    await db.commit()
    return ForgotPasswordResponse(
        message="If an account exists for that email, password reset instructions have been generated.",
        delivery=delivery.delivery,
        preview_url=delivery.preview_url,
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(request: ResetPasswordRequest, db: DbSession):
    _validate_new_password(request.new_password)
    token = await consume_password_reset_token(db, request.token)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or expired.",
        )

    user = (
        await db.execute(select(User).where(User.id == token.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or expired.",
        )

    user.password_hash = argon2.hash(request.new_password)
    await revoke_other_password_reset_tokens(db, user.id)
    await db.commit()
    return MessageResponse(message="Password updated. You can sign in with the new password.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(request: ChangePasswordRequest, user: CurrentUser, db: DbSession):
    _validate_new_password(request.new_password)
    if not argon2.verify(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.password_hash = argon2.hash(request.new_password)
    await revoke_other_password_reset_tokens(db, user.id)
    await db.commit()
    return MessageResponse(message="Password changed successfully.")


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser):
    return UserResponse(id=str(user.id), email=user.email, display_name=user.display_name)
