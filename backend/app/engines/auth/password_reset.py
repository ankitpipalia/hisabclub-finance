import asyncio
import hashlib
import logging
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class PasswordResetDelivery:
    delivery: str
    preview_url: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def build_password_reset_url(raw_token: str) -> str:
    base = settings.web_base_url.rstrip("/")
    return f"{base}/reset-password?token={quote(raw_token)}"


async def issue_password_reset_token(db: AsyncSession, user: User) -> tuple[str, PasswordResetToken]:
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )

    raw_token = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=_utcnow() + timedelta(minutes=settings.password_reset_token_expire_minutes),
    )
    db.add(token)
    await db.flush()
    return raw_token, token


async def consume_password_reset_token(
    db: AsyncSession,
    raw_token: str,
) -> PasswordResetToken | None:
    hashed = _hash_token(raw_token)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hashed,
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        return None
    if token.used_at is not None:
        return None
    if token.expires_at <= _utcnow():
        return None
    token.used_at = _utcnow()
    return token


async def send_password_reset_instructions(
    user: User,
    reset_url: str,
) -> PasswordResetDelivery:
    if settings.smtp_host.strip():
        await asyncio.to_thread(_send_password_reset_email_sync, user, reset_url)
        return PasswordResetDelivery(delivery="email")

    logger.warning(
        "SMTP is not configured. Password reset preview for %s: %s",
        user.email,
        reset_url,
    )
    if settings.debug or settings.local_only_mode:
        return PasswordResetDelivery(delivery="preview", preview_url=reset_url)
    return PasswordResetDelivery(delivery="unavailable")


def _send_password_reset_email_sync(user: User, reset_url: str) -> None:
    msg = EmailMessage()
    from_email = settings.smtp_from_email.strip() or settings.smtp_username.strip()
    if not from_email:
        raise RuntimeError("SMTP_FROM_EMAIL or SMTP_USERNAME must be configured for password reset email")

    display_from = settings.smtp_from_name.strip()
    msg["From"] = f"{display_from} <{from_email}>" if display_from else from_email
    msg["To"] = user.email
    msg["Subject"] = "Reset your HisabClub password"
    msg.set_content(
        "\n".join(
            [
                f"Hi {user.display_name},",
                "",
                "A password reset was requested for your HisabClub account.",
                "Use the link below to set a new password:",
                reset_url,
                "",
                f"This link expires in {settings.password_reset_token_expire_minutes} minutes.",
                "If you did not request this, you can ignore this email.",
            ]
        )
    )

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            _smtp_login(server)
            server.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        if settings.smtp_use_starttls:
            server.starttls()
        _smtp_login(server)
        server.send_message(msg)


def _smtp_login(server: smtplib.SMTP) -> None:
    if settings.smtp_username.strip():
        server.login(settings.smtp_username, settings.smtp_password)


async def revoke_other_password_reset_tokens(db: AsyncSession, user_id: object) -> None:
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=_utcnow())
    )
