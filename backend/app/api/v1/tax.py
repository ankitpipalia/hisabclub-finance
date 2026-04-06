from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.engines.intake.tax_document_parser import extract_tax_document_metadata
from app.engines.parser.pdf_utils import decrypt_pdf
from app.engines.parser.pdf_utils import extract_text as extract_pdf_text
from app.engines.tax.ais_parser import parse_ais_document
from app.engines.tax.form16_parser import parse_form16_document
from app.engines.tax.form_26as_parser import parse_form_26as_document
from app.engines.tax.verification import cross_verify_tax
from app.models.document_artifact import DocumentArtifact
from app.models.tax_portal_data import TaxPortalData
from app.schemas.tax import (
    TaxPortalDataResponse,
    TaxPortalUploadResponse,
    TaxVerificationCheck,
    TaxVerificationResponse,
)

router = APIRouter()

_SUPPORTED_PORTAL_TYPES = {"form_26as", "ais", "tis", "form_16"}


def _to_portal_data_response(row: TaxPortalData) -> TaxPortalDataResponse:
    return TaxPortalDataResponse(
        id=str(row.id),
        document_artifact_id=str(row.document_artifact_id) if row.document_artifact_id else None,
        document_type=row.document_type,
        assessment_year=row.assessment_year,
        financial_year=row.financial_year,
        source_name=row.source_name,
        pan_masked=row.pan_masked,
        document_date=row.document_date,
        extracted_json=row.extracted_json or {},
        verification_json=row.verification_json,
        status=row.status,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _extract_plain_text(content: bytes, filename: str) -> str:
    suffix = os.path.splitext(filename)[1].lower()
    if suffix == ".csv":
        decoded = content.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(decoded))
        return "\n".join(" | ".join(row) for row in reader)
    if suffix == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                chunks: list[str] = []
                for name in zf.namelist():
                    if not name.endswith(".xml"):
                        continue
                    if "worksheets/" not in name and not name.endswith("sharedStrings.xml"):
                        continue
                    xml_text = zf.read(name).decode("utf-8", errors="ignore")
                    chunks.extend(re.findall(r">([^<>]{1,200})<", xml_text))
                return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())
        except zipfile.BadZipFile:
            return content.decode("utf-8", errors="ignore")
    return content.decode("utf-8", errors="ignore")


def _parse_portal_payload(document_type: str, text: str, file_name: str) -> dict:
    if document_type == "form_26as":
        return parse_form_26as_document(text, source_filename=file_name)
    if document_type == "form_16":
        return parse_form16_document(text, source_filename=file_name)
    if document_type in {"ais", "tis"}:
        return parse_ais_document(text, source_filename=file_name, document_type=document_type)
    raise ValueError(f"Unsupported document_type '{document_type}'")


@router.post("/upload-portal-document", response_model=TaxPortalUploadResponse)
async def upload_portal_document(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    financial_year: str | None = Form(default=None),
    password: str | None = Form(default=None),
    force_reprocess: bool = Form(default=False),
):
    normalized_type = (document_type or "").strip().lower()
    if normalized_type not in _SUPPORTED_PORTAL_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported tax document type.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file upload.")
    file_name = file.filename or f"{normalized_type}-{uuid.uuid4()}"
    file_ext = os.path.splitext(file_name)[1].lower() or ".bin"
    file_hash = hashlib.sha256(content).hexdigest()

    existing_artifact = (
        await db.execute(
            select(DocumentArtifact).where(
                DocumentArtifact.user_id == user.id,
                DocumentArtifact.file_hash_sha256 == file_hash,
                DocumentArtifact.doc_type == normalized_type,
            )
        )
    ).scalar_one_or_none()
    if existing_artifact is not None and not force_reprocess:
        existing_row = (
            await db.execute(
                select(TaxPortalData).where(
                    TaxPortalData.user_id == user.id,
                    TaxPortalData.document_artifact_id == existing_artifact.id,
                )
            )
        ).scalar_one_or_none()
        if existing_row is not None:
            return TaxPortalUploadResponse(
                artifact_id=str(existing_artifact.id),
                portal_data_id=str(existing_row.id),
                document_type=normalized_type,
                financial_year=existing_row.financial_year,
                message="This portal document is already registered.",
            )

    text = ""
    if file_ext == ".pdf":
        decrypted = decrypt_pdf(content, password=password)
        pages = extract_pdf_text(decrypted)
        text = "\n\n".join(page for page in pages if page)
    else:
        text = _extract_plain_text(content, file_name)
    extracted_json = _parse_portal_payload(normalized_type, text, file_name)
    generic_metadata = extract_tax_document_metadata(
        doc_type="tax_form" if normalized_type == "form_16" else normalized_type,
        text=text,
        source_filename=file_name,
    )
    effective_fy = financial_year or extracted_json.get("financial_year") or generic_metadata.get("financial_year")

    storage_dir = os.path.join(settings.upload_dir, str(user.id), "artifacts")
    os.makedirs(storage_dir, exist_ok=True)
    artifact_id = existing_artifact.id if existing_artifact else uuid.uuid4()
    storage_path = os.path.join(storage_dir, f"{artifact_id}{file_ext}")
    with open(storage_path, "wb") as out:
        out.write(content)

    if existing_artifact is None:
        artifact = DocumentArtifact(
            id=artifact_id,
            user_id=user.id,
            file_path=storage_path,
            file_name=file_name,
            file_ext=file_ext.lstrip("."),
            file_hash_sha256=file_hash,
            file_size_bytes=len(content),
            doc_type=normalized_type,
            status="parsed",
            parse_message="Portal document parsed for tax verification.",
            metadata_json={**generic_metadata, **extracted_json},
            processed_at=datetime.now(timezone.utc),
        )
        db.add(artifact)
        await db.flush()
    else:
        artifact = existing_artifact
        artifact.file_path = storage_path
        artifact.file_name = file_name
        artifact.file_ext = file_ext.lstrip(".")
        artifact.file_size_bytes = len(content)
        artifact.status = "parsed"
        artifact.parse_message = "Portal document parsed for tax verification."
        artifact.metadata_json = {**generic_metadata, **extracted_json}
        artifact.processed_at = datetime.now(timezone.utc)
        await db.flush()

    portal_row = (
        await db.execute(
            select(TaxPortalData).where(
                TaxPortalData.user_id == user.id,
                TaxPortalData.document_artifact_id == artifact.id,
            )
        )
    ).scalar_one_or_none()
    if portal_row is None:
        portal_row = TaxPortalData(
            user_id=user.id,
            document_artifact_id=artifact.id,
            document_type=normalized_type,
            financial_year=effective_fy,
            assessment_year=generic_metadata.get("assessment_year"),
            source_name=file_name,
            pan_masked=generic_metadata.get("pan_masked"),
            document_date=None,
            extracted_json=extracted_json,
            status="parsed",
        )
        db.add(portal_row)
    else:
        portal_row.document_type = normalized_type
        portal_row.financial_year = effective_fy
        portal_row.assessment_year = generic_metadata.get("assessment_year")
        portal_row.source_name = file_name
        portal_row.pan_masked = generic_metadata.get("pan_masked")
        portal_row.extracted_json = extracted_json
        portal_row.status = "parsed"
    await db.flush()

    return TaxPortalUploadResponse(
        artifact_id=str(artifact.id),
        portal_data_id=str(portal_row.id),
        document_type=normalized_type,
        financial_year=effective_fy,
        message="Portal document uploaded and parsed.",
    )


@router.get("/verification/{financial_year}", response_model=TaxVerificationResponse)
async def get_tax_verification(financial_year: str, user: CurrentUser, db: DbSession):
    result = await cross_verify_tax(db, user_id=user.id, financial_year=financial_year)
    return TaxVerificationResponse(
        financial_year=result["financial_year"],
        tax_report=result["tax_report"],
        portal_data=[_to_portal_data_response(row) for row in result["portal_data"]],
        checks=[TaxVerificationCheck(**check) for check in result["checks"]],
        discrepancies=[TaxVerificationCheck(**check) for check in result["discrepancies"]],
    )


@router.get("/portal-data/{financial_year}", response_model=list[TaxPortalDataResponse])
async def list_tax_portal_data(financial_year: str, user: CurrentUser, db: DbSession):
    rows = (
        await db.execute(
            select(TaxPortalData).where(
                TaxPortalData.user_id == user.id,
                TaxPortalData.financial_year == financial_year,
            )
        )
    ).scalars().all()
    return [_to_portal_data_response(row) for row in rows]


@router.get("/discrepancies/{financial_year}", response_model=list[TaxVerificationCheck])
async def list_tax_discrepancies(financial_year: str, user: CurrentUser, db: DbSession):
    result = await cross_verify_tax(db, user_id=user.id, financial_year=financial_year)
    return [TaxVerificationCheck(**check) for check in result["discrepancies"]]
