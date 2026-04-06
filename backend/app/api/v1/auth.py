import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from passlib.hash import argon2
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.account.service import ensure_account_record
from app.engines.account.data_reset import clear_user_data_everywhere
from app.engines.auth.password_reset import (
    build_password_reset_url,
    consume_password_reset_token,
    issue_password_reset_token,
    revoke_other_password_reset_tokens,
    send_password_reset_instructions,
)
from app.models.user import User
from app.security.crypto import encrypt_text
from app.schemas.auth import (
    ChangePasswordRequest,
    ClearUserDataRequest,
    ClearUserDataResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MessageResponse,
    OnboardingBanksRequest,
    OnboardingProfileRequest,
    OnboardingStatusResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SetupRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()
_PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")


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


def _normalize_pan_number(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if not normalized:
        return None
    if not _PAN_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PAN must match the format ABCDE1234F.",
        )
    return normalized


def _profile_complete(user: User) -> bool:
    return bool((user.first_name or "").strip() and (user.date_of_birth or "").strip())


async def _create_user_account(
    db: DbSession,
    *,
    email: str,
    display_name: str,
    password: str,
    first_name: str | None = None,
    last_name: str | None = None,
    date_of_birth: str | None = None,
    pan_number: str | None = None,
) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    normalized_pan = _normalize_pan_number(pan_number)
    user = User(
        email=email,
        display_name=display_name,
        password_hash=argon2.hash(password),
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        pan_number_encrypted=encrypt_text(normalized_pan) if normalized_pan else None,
        onboarding_completed=False,
        onboarding_step=1,
    )
    db.add(user)
    await db.flush()
    return user


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

    user = await _create_user_account(
        db,
        email=request.email,
        display_name=request.display_name,
        password=request.password,
        first_name=request.first_name,
        last_name=request.last_name,
        date_of_birth=request.date_of_birth,
        pan_number=request.pan_number,
    )

    return create_tokens(str(user.id))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: DbSession):
    _validate_new_password(request.password)
    user = await _create_user_account(
        db,
        email=request.email,
        display_name=request.display_name,
        password=request.password,
        first_name=request.first_name,
        last_name=request.last_name,
        date_of_birth=request.date_of_birth,
        pan_number=request.pan_number,
    )
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


@router.post("/clear-data", response_model=ClearUserDataResponse)
async def clear_my_data(request: ClearUserDataRequest, user: CurrentUser, db: DbSession):
    confirmation = (request.confirmation or "").strip().lower()
    if confirmation != "clear my data":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation must be exactly "CLEAR MY DATA".',
        )
    if not argon2.verify(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    try:
        result = await clear_user_data_everywhere(db, user_id=user.id)
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear user data due to a database error. Please try again.",
        ) from exc

    return ClearUserDataResponse(
        message="All user-scoped data, files, and local LLM context have been cleared.",
        deleted_rows=result.deleted_rows,
        deleted_files=result.deleted_files,
        deleted_directories=result.deleted_directories,
        file_delete_errors=result.file_delete_errors,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser):
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        first_name=user.first_name,
        last_name=user.last_name,
        onboarding_completed=user.onboarding_completed,
        onboarding_step=user.onboarding_step,
    )


@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(user: CurrentUser, db: DbSession):
    from app.models.account import Account

    account_count = (
        await db.execute(select(func.count(Account.id)).where(Account.user_id == user.id))
    ).scalar() or 0
    return OnboardingStatusResponse(
        completed=bool(user.onboarding_completed),
        current_step=int(user.onboarding_step or 0),
        profile_complete=_profile_complete(user),
        accounts_count=int(account_count),
    )


@router.post("/onboarding/profile", response_model=UserResponse)
async def update_onboarding_profile(request: OnboardingProfileRequest, user: CurrentUser, db: DbSession):
    if request.first_name is not None:
        user.first_name = request.first_name.strip() or None
    if request.last_name is not None:
        user.last_name = request.last_name.strip() or None
    if request.date_of_birth is not None:
        user.date_of_birth = request.date_of_birth.strip() or None
    if request.pan_number is not None:
        normalized_pan = _normalize_pan_number(request.pan_number)
        user.pan_number_encrypted = encrypt_text(normalized_pan) if normalized_pan else None
    user.onboarding_step = max(int(user.onboarding_step or 0), 1)
    await db.flush()
    return await get_me(user)


@router.post("/onboarding/banks", response_model=MessageResponse)
async def save_onboarding_banks(request: OnboardingBanksRequest, user: CurrentUser, db: DbSession):
    created = 0
    for bank in request.banks:
        for item in bank.accounts:
            account = await ensure_account_record(
                db,
                user_id=user.id,
                bank_name=bank.institution_name,
                account_type=item.account_type,
                account_number_masked=item.account_number_masked,
            )
            if account is None:
                continue
            if item.nickname:
                account.nickname = item.nickname.strip() or None
            created += 1
    user.onboarding_step = max(int(user.onboarding_step or 0), 3)
    await db.flush()
    return MessageResponse(message=f"Saved {created} onboarding account entries.")


@router.post("/onboarding/complete", response_model=OnboardingStatusResponse)
async def complete_onboarding(user: CurrentUser, db: DbSession):
    user.onboarding_completed = True
    user.onboarding_step = 4
    await db.flush()
    return await get_onboarding_status(user, db)
