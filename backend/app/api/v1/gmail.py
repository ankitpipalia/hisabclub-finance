"""Gmail integration API routes — OAuth flow, sync, and allowlist management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.engines.gmail.service import GmailService
from app.models.connected_account import ConnectedAccount

router = APIRouter()
gmail_service = GmailService()


# ─── Schemas ──────────────────────────────────────────


class ConnectResponse(BaseModel):
    auth_url: str


class SyncResponse(BaseModel):
    emails_found: int
    pdfs_saved: int
    provider_email: str | None = None
    error: str | None = None


class AllowlistUpdate(BaseModel):
    senders: list[str]


class AllowlistResponse(BaseModel):
    account_id: str
    provider_email: str | None
    senders: list[str]


# ─── Routes ───────────────────────────────────────────


@router.post("/connect", response_model=ConnectResponse)
async def connect_gmail(user: CurrentUser):
    """Start Gmail OAuth flow. Returns the auth URL to redirect the user to."""
    try:
        auth_url = await gmail_service.start_oauth(user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return ConnectResponse(auth_url=auth_url)


@router.get("/callback")
async def gmail_callback(
    db: DbSession,
    code: str = Query(...),
    state: str = Query(...),
):
    """Handle the OAuth callback from Google.

    The state parameter contains the user_id.
    """
    try:
        user_id = uuid.UUID(state)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    try:
        account = await gmail_service.handle_callback(db, user_id, code)
        return {
            "status": "connected",
            "account_id": str(account.id),
            "provider_email": account.provider_email,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth callback failed: {exc}",
        )


@router.post("/sync", response_model=SyncResponse)
async def sync_gmail(db: DbSession, user: CurrentUser):
    """Trigger a manual sync of statement emails from Gmail.

    Fetches PDFs from all active connected Gmail accounts for the user.
    """
    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user.id,
            ConnectedAccount.provider == "gmail",
            ConnectedAccount.status == "active",
        )
    )
    accounts = result.scalars().all()

    if not accounts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Gmail accounts connected. Use POST /gmail/connect first.",
        )

    total_emails = 0
    total_pdfs = 0
    provider_email = None
    error = None

    for account in accounts:
        sync_result = await gmail_service.sync_statements(db, user.id, account.id)
        total_emails += sync_result.get("emails_found", 0)
        total_pdfs += sync_result.get("pdfs_saved", 0)
        provider_email = sync_result.get("provider_email", provider_email)
        if sync_result.get("error"):
            error = sync_result["error"]

    return SyncResponse(
        emails_found=total_emails,
        pdfs_saved=total_pdfs,
        provider_email=provider_email,
        error=error,
    )


@router.get("/allowlist", response_model=list[AllowlistResponse])
async def get_allowlist(db: DbSession, user: CurrentUser):
    """Get the sender allowlist for all connected Gmail accounts."""
    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user.id,
            ConnectedAccount.provider == "gmail",
        )
    )
    accounts = result.scalars().all()
    return [
        AllowlistResponse(
            account_id=str(a.id),
            provider_email=a.provider_email,
            senders=a.sender_allowlist or [],
        )
        for a in accounts
    ]


@router.put("/allowlist", response_model=AllowlistResponse)
async def update_allowlist(
    db: DbSession,
    user: CurrentUser,
    body: AllowlistUpdate,
    account_id: str = Query(..., description="Connected account ID"),
):
    """Update the sender allowlist for a connected Gmail account."""
    try:
        acct_uuid = uuid.UUID(account_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid account_id",
        )

    # Verify ownership
    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.id == acct_uuid,
            ConnectedAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connected account not found",
        )

    updated = await gmail_service.update_allowlist(db, acct_uuid, body.senders)
    return AllowlistResponse(
        account_id=str(updated.id),
        provider_email=updated.provider_email,
        senders=updated.sender_allowlist or [],
    )
