"""Gmail service — OAuth flow, email sync, and PDF attachment extraction."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.connected_account import ConnectedAccount
from app.models.raw_pdf import RawPdf

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_client_config() -> dict:
    """Build the OAuth client config dict from settings."""
    if not settings.gmail_client_id.strip():
        raise ValueError(
            "Gmail OAuth is not configured: missing GMAIL_CLIENT_ID in backend .env"
        )
    if not settings.gmail_client_secret.strip():
        raise ValueError(
            "Gmail OAuth is not configured: missing GMAIL_CLIENT_SECRET in backend .env"
        )
    if not settings.gmail_redirect_uri.strip():
        raise ValueError(
            "Gmail OAuth is not configured: missing GMAIL_REDIRECT_URI in backend .env"
        )

    return {
        "web": {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.gmail_redirect_uri],
        }
    }


class GmailService:
    """Handles Gmail OAuth, email sync, and PDF attachment extraction."""

    async def start_oauth(self, user_id: uuid.UUID) -> str:
        """Initiate the OAuth flow and return the authorization URL.

        The user_id is encoded in the state parameter so we can link
        the callback to the correct user.
        """
        flow = Flow.from_client_config(
            _get_client_config(),
            scopes=SCOPES,
            redirect_uri=settings.gmail_redirect_uri,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=str(user_id),
        )
        return auth_url

    async def handle_callback(
        self, db: AsyncSession, user_id: uuid.UUID, auth_code: str
    ) -> ConnectedAccount:
        """Exchange the auth code for credentials and save them."""
        flow = Flow.from_client_config(
            _get_client_config(),
            scopes=SCOPES,
            redirect_uri=settings.gmail_redirect_uri,
        )
        flow.fetch_token(code=auth_code)
        creds = flow.credentials

        # Get the user's email from Gmail API
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        provider_email = profile.get("emailAddress", "")

        # Serialize credentials
        creds_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        }
        # TODO: encrypt credentials_enc in production
        creds_json = json.dumps(creds_data)

        # Check if an account already exists for this user + provider
        result = await db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.provider == "gmail",
                ConnectedAccount.provider_email == provider_email,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.credentials_enc = creds_json
            existing.status = "active"
            await db.flush()
            return existing

        # Default sender allowlist — common Indian bank statement email senders
        default_allowlist = [
            "alerts@hdfcbank.net",
            "creditcard@hdfcbank.com",
            "alerts@axisbank.com",
            "statements@axisbank.com",
            "estatement@sbi.co.in",
            "donotreply@icicibank.com",
        ]

        account = ConnectedAccount(
            user_id=user_id,
            provider="gmail",
            provider_email=provider_email,
            credentials_enc=creds_json,
            sender_allowlist=default_allowlist,
            status="active",
        )
        db.add(account)
        await db.flush()
        return account

    def _get_credentials(self, account: ConnectedAccount) -> Credentials | None:
        """Deserialize and refresh credentials if needed."""
        if not account.credentials_enc:
            return None

        creds_data = json.loads(account.credentials_enc)
        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=creds_data.get("scopes"),
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return creds

    async def sync_statements(
        self, db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> dict:
        """Fetch new statement emails with PDF attachments.

        Lists messages from allowed senders, downloads PDF attachments,
        saves them as RawPdf with source_type='email_attachment', and
        triggers parsing for each.

        Returns summary dict with counts.
        """
        result = await db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.id == account_id,
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.status == "active",
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            return {
                "error": "Connected account not found or inactive",
                "emails_found": 0,
                "pdfs_saved": 0,
            }

        creds = self._get_credentials(account)
        if not creds:
            return {"error": "Invalid credentials", "emails_found": 0, "pdfs_saved": 0}

        service = build("gmail", "v1", credentials=creds)

        # Build query from sender allowlist
        senders = account.sender_allowlist or []
        if not senders:
            return {"error": "No senders in allowlist", "emails_found": 0, "pdfs_saved": 0}

        sender_query = " OR ".join(f"from:{s}" for s in senders)
        query = f"({sender_query}) has:attachment filename:pdf"

        # If we've synced before, only fetch newer messages
        if account.last_sync_at:
            epoch_secs = int(account.last_sync_at.timestamp())
            query += f" after:{epoch_secs}"

        emails_found = 0
        pdfs_saved = 0

        try:
            messages_result = service.users().messages().list(
                userId="me", q=query, maxResults=50
            ).execute()
            messages = messages_result.get("messages", [])
            emails_found = len(messages)

            for msg_meta in messages:
                msg = service.users().messages().get(
                    userId="me", id=msg_meta["id"]
                ).execute()

                # Find PDF attachments
                for part in msg.get("payload", {}).get("parts", []):
                    filename = part.get("filename", "")
                    if not filename.lower().endswith(".pdf"):
                        continue

                    attachment_id = part.get("body", {}).get("attachmentId")
                    if not attachment_id:
                        continue

                    # Download attachment
                    attachment = service.users().messages().attachments().get(
                        userId="me", messageId=msg_meta["id"], id=attachment_id
                    ).execute()
                    file_data = base64.urlsafe_b64decode(attachment["data"])

                    # Compute hash and check for duplicates
                    file_hash = hashlib.sha256(file_data).hexdigest()
                    dup_check = await db.execute(
                        select(RawPdf.id)
                        .where(
                            RawPdf.user_id == user_id,
                            RawPdf.file_hash_sha256 == file_hash,
                        )
                        .limit(1)
                    )
                    if dup_check.scalar_one_or_none() is not None:
                        logger.info(
                            "Skipping duplicate PDF: %s (hash: %s)",
                            filename,
                            file_hash[:12],
                        )
                        continue

                    # Save file to disk
                    upload_dir = os.path.join(settings.upload_dir, str(user_id))
                    os.makedirs(upload_dir, exist_ok=True)
                    storage_filename = f"{uuid.uuid4().hex}_{filename}"
                    storage_path = os.path.join(upload_dir, storage_filename)
                    with open(storage_path, "wb") as f:
                        f.write(file_data)

                    # Save RawPdf record
                    raw_pdf = RawPdf(
                        user_id=user_id,
                        source_type="email_attachment",
                        original_filename=filename,
                        file_hash_sha256=file_hash,
                        storage_path=storage_path,
                        file_size_bytes=len(file_data),
                        is_password_protected=False,
                    )
                    db.add(raw_pdf)
                    await db.flush()
                    pdfs_saved += 1

                    # Trigger statement parsing
                    try:
                        from app.engines.parser.base import parse_statement

                        await parse_statement(
                            db=db,
                            user_id=user_id,
                            pdf_id=raw_pdf.id,
                            pdf_content=file_data,
                        )
                    except Exception as parse_exc:
                        logger.warning(
                            "Failed to parse email PDF %s: %s", filename, parse_exc
                        )

            # Update last sync timestamp
            account.last_sync_at = datetime.now(timezone.utc)
            await db.flush()

        except Exception as exc:
            logger.error("Gmail sync error: %s", exc)
            return {"error": str(exc), "emails_found": emails_found, "pdfs_saved": pdfs_saved}

        return {
            "emails_found": emails_found,
            "pdfs_saved": pdfs_saved,
            "provider_email": account.provider_email,
        }

    async def update_allowlist(
        self, db: AsyncSession, account_id: uuid.UUID, senders: list[str]
    ) -> ConnectedAccount:
        """Update the sender allowlist for a connected account."""
        result = await db.execute(
            select(ConnectedAccount).where(ConnectedAccount.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError("Connected account not found")

        account.sender_allowlist = senders
        await db.flush()
        return account
