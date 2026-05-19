from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone

from decimal import Decimal, InvalidOperation

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
from app.engines.insights.tax_planning import compute_tax_planning_summary
from app.engines.tax.deductions import (
    WhatIfScenario as _WhatIfScenario,
    compute_utilization,
    what_if,
)
from app.engines.tax.recommender.itr_form import ItrInputs as _ItrInputs
from app.engines.tax.recommender.itr_form import recommend_itr_form
from app.engines.tax.reconcile.wire import run_all_reconciliations
from app.engines.tax.regime import TaxInputs as _TaxInputs
from app.engines.tax.regime import RegimeComparison as _RegimeComparison
from app.engines.tax.regime import RegimeResult as _RegimeResult
from app.engines.tax.regime import compare as _compare_regimes
from app.engines.tax.rules import get_rules as _get_tax_rules
from app.engines.tax.rules import supported_fys as _supported_fys
from app.engines.tax.verification import cross_verify_tax
from app.models.document_artifact import DocumentArtifact
from app.models.tax_portal_data import TaxPortalData
from app.schemas.tax import (
    DeductionUtilizationItem,
    DeductionUtilizationResponse,
    ItrRecommendationInputs,
    ItrRecommendationResponse,
    ReconciliationBundleResponse,
    ReconciliationLineResponse,
    ReconciliationReportResponse,
    RegimeComparisonResponse,
    RegimeInputs,
    RegimeResultResponse,
    TaxPlanningResponse,
    TaxPlanningSectionResponse,
    TaxPortalDataResponse,
    TaxPortalUploadResponse,
    TaxVerificationCheck,
    TaxVerificationResponse,
    WhatIfResponse,
    WhatIfScenarioRequest,
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


@router.get("/planning/{financial_year}", response_model=TaxPlanningResponse)
async def get_tax_planning(
    financial_year: str,
    user: CurrentUser,
    db: DbSession,
):
    """YTD deduction-section tracking against statutory limits.

    Rule-based on category/merchant names — designed to surface "you've used
    67% of your 80C limit; ₹50k remaining" in real time so users plan during
    the financial year, not at filing time.
    """
    try:
        sections = await compute_tax_planning_summary(
            db, user_id=user.id, financial_year=financial_year,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return TaxPlanningResponse(
        financial_year=financial_year,
        sections=[
            TaxPlanningSectionResponse(
                section=s.section,
                label=s.label,
                ytd_amount=str(s.ytd_amount),
                limit=str(s.limit),
                remaining=str(s.remaining) if s.remaining is not None else None,
                progress_pct=s.progress_pct,
            )
            for s in sections
        ],
    )


# --------------------------------------------------------------------------- #
# Phase 2 (master_plan_2026.md §10): FY-versioned tax engine — regime
# comparator, deduction utilization, ITR form recommender, what-if optimizer.
# --------------------------------------------------------------------------- #


def _to_decimal(name: str, raw: str | None) -> Decimal:
    if raw is None or raw == "":
        return Decimal("0")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decimal for {name}: {raw!r}",
        ) from exc


def _to_inputs(body: RegimeInputs) -> _TaxInputs:
    return _TaxInputs(
        gross_salary=_to_decimal("gross_salary", body.gross_salary),
        interest_income=_to_decimal("interest_income", body.interest_income),
        dividend_income=_to_decimal("dividend_income", body.dividend_income),
        rental_income_net=_to_decimal("rental_income_net", body.rental_income_net),
        other_income=_to_decimal("other_income", body.other_income),
        capital_gain_equity_stcg=_to_decimal(
            "capital_gain_equity_stcg", body.capital_gain_equity_stcg
        ),
        capital_gain_equity_ltcg=_to_decimal(
            "capital_gain_equity_ltcg", body.capital_gain_equity_ltcg
        ),
        capital_gain_other=_to_decimal("capital_gain_other", body.capital_gain_other),
        deduction_80c=_to_decimal("deduction_80c", body.deduction_80c),
        deduction_80ccd_1b=_to_decimal("deduction_80ccd_1b", body.deduction_80ccd_1b),
        deduction_80ccd_2=_to_decimal("deduction_80ccd_2", body.deduction_80ccd_2),
        deduction_80d_self=_to_decimal("deduction_80d_self", body.deduction_80d_self),
        deduction_80d_parents=_to_decimal(
            "deduction_80d_parents", body.deduction_80d_parents
        ),
        deduction_80e=_to_decimal("deduction_80e", body.deduction_80e),
        deduction_80g=_to_decimal("deduction_80g", body.deduction_80g),
        deduction_80gg=_to_decimal("deduction_80gg", body.deduction_80gg),
        deduction_80tta_or_ttb=_to_decimal(
            "deduction_80tta_or_ttb", body.deduction_80tta_or_ttb
        ),
        home_loan_interest_self=_to_decimal(
            "home_loan_interest_self", body.home_loan_interest_self
        ),
        home_loan_interest_letout=_to_decimal(
            "home_loan_interest_letout", body.home_loan_interest_letout
        ),
        is_salaried=body.is_salaried,
        is_pensioner=body.is_pensioner,
        is_senior=body.is_senior,
    )


def _serialize_regime_result(result: _RegimeResult) -> RegimeResultResponse:
    return RegimeResultResponse(
        regime=result.regime,
        fy=result.fy,
        gross_total_income=str(result.gross_total_income),
        standard_deduction=str(result.standard_deduction),
        section_24b_deduction=str(result.section_24b_deduction),
        chapter_via_deduction=str(result.chapter_via_deduction),
        taxable_income=str(result.taxable_income),
        tax_on_slabs=str(result.tax_on_slabs),
        tax_on_special_rate_income=str(result.tax_on_special_rate_income),
        base_tax=str(result.base_tax),
        rebate_87a=str(result.rebate_87a),
        tax_after_rebate=str(result.tax_after_rebate),
        surcharge=str(result.surcharge),
        cess=str(result.cess),
        total_tax=str(result.total_tax),
        notes=list(result.notes),
    )


def _serialize_comparison(comparison: _RegimeComparison) -> RegimeComparisonResponse:
    rules = _get_tax_rules(comparison.fy)
    return RegimeComparisonResponse(
        fy=comparison.fy,
        old=_serialize_regime_result(comparison.old),
        new=_serialize_regime_result(comparison.new),
        recommendation=comparison.recommendation,
        delta=str(comparison.delta),
        sources=list(rules.sources),
    )


def _ensure_supported_fy(fy: str) -> None:
    try:
        _get_tax_rules(fy)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported financial year {fy!r}. "
                f"Supported: {_supported_fys()}"
            ),
        ) from exc


@router.post("/regime/compare", response_model=RegimeComparisonResponse)
async def post_regime_compare(
    body: RegimeInputs,
    fy: str,
    user: CurrentUser,  # noqa: ARG001 — auth-gate only
):
    """Compute old vs new regime side-by-side for the given FY + inputs.

    No DB access. The user's `auth-gate only` ensures only authenticated
    callers reach this endpoint, but the calculation is a pure function so
    it can be cached at the edge later.
    """
    _ensure_supported_fy(fy)
    comparison = _compare_regimes(fy, _to_inputs(body))
    return _serialize_comparison(comparison)


@router.get("/deductions/utilization", response_model=DeductionUtilizationResponse)
async def get_deduction_utilization(
    fy: str,
    user: CurrentUser,  # noqa: ARG001
    deduction_80c: str = "0",
    deduction_80ccd_1b: str = "0",
    deduction_80d_self: str = "0",
    deduction_80d_parents: str = "0",
    deduction_80e: str = "0",
    deduction_80tta_or_ttb: str = "0",
    home_loan_interest_self: str = "0",
    is_senior: bool = False,
):
    _ensure_supported_fy(fy)
    claims = {
        "deduction_80c": _to_decimal("deduction_80c", deduction_80c),
        "deduction_80ccd_1b": _to_decimal("deduction_80ccd_1b", deduction_80ccd_1b),
        "deduction_80d_self": _to_decimal("deduction_80d_self", deduction_80d_self),
        "deduction_80d_parents": _to_decimal(
            "deduction_80d_parents", deduction_80d_parents
        ),
        "deduction_80e": _to_decimal("deduction_80e", deduction_80e),
        "deduction_80tta_or_ttb": _to_decimal(
            "deduction_80tta_or_ttb", deduction_80tta_or_ttb
        ),
        "home_loan_interest_self": _to_decimal(
            "home_loan_interest_self", home_loan_interest_self
        ),
    }
    report = compute_utilization(fy, claims, is_senior=is_senior)
    return DeductionUtilizationResponse(
        fy=report.fy,
        items=[
            DeductionUtilizationItem(
                section=item.section,
                cap=str(item.cap) if item.cap is not None else None,
                claimed=str(item.claimed),
                remaining=str(item.remaining) if item.remaining is not None else None,
                description=item.description,
            )
            for item in report.items
        ],
    )


@router.post("/itr/recommend", response_model=ItrRecommendationResponse)
async def post_itr_recommend(
    body: ItrRecommendationInputs,
    user: CurrentUser,  # noqa: ARG001
):
    inputs = _ItrInputs(
        total_income=_to_decimal("total_income", body.total_income),
        has_business_income=body.has_business_income,
        opted_into_presumptive_44ad_44ada=body.opted_into_presumptive_44ad_44ada,
        has_capital_gains_non_112a_carveout=body.has_capital_gains_non_112a_carveout,
        has_more_than_one_house_property=body.has_more_than_one_house_property,
        has_brought_forward_house_property_loss=body.has_brought_forward_house_property_loss,
        has_foreign_asset_or_income=body.has_foreign_asset_or_income,
        is_director_or_holds_unlisted_shares=body.is_director_or_holds_unlisted_shares,
        agricultural_income=_to_decimal(
            "agricultural_income", body.agricultural_income
        ),
        is_resident=body.is_resident,
    )
    rec = recommend_itr_form(inputs)
    return ItrRecommendationResponse(
        form=rec.form,
        reasons=list(rec.reasons),
        blockers_for_itr1=list(rec.blockers_for_itr1),
    )


@router.post("/optimizer/whatif", response_model=WhatIfResponse)
async def post_what_if(
    body: WhatIfScenarioRequest,
    user: CurrentUser,  # noqa: ARG001
):
    _ensure_supported_fy(body.fy)
    baseline_inputs = _to_inputs(body.baseline)
    scenario = _WhatIfScenario(
        deduction_80c=_to_decimal("scenario_80c", body.scenario_80c),
        deduction_80ccd_1b=_to_decimal(
            "scenario_80ccd_1b", body.scenario_80ccd_1b
        ),
        deduction_80d_self=_to_decimal(
            "scenario_80d_self", body.scenario_80d_self
        ),
        deduction_80d_parents=_to_decimal(
            "scenario_80d_parents", body.scenario_80d_parents
        ),
        deduction_80e=_to_decimal("scenario_80e", body.scenario_80e),
        deduction_80g=_to_decimal("scenario_80g", body.scenario_80g),
        deduction_80tta_or_ttb=_to_decimal(
            "scenario_80tta_or_ttb", body.scenario_80tta_or_ttb
        ),
        home_loan_interest_self=_to_decimal(
            "scenario_home_loan_interest_self", body.scenario_home_loan_interest_self
        ),
    )
    result = what_if(body.fy, baseline_inputs, scenario)
    return WhatIfResponse(
        fy=result.fy,
        baseline=_serialize_comparison(result.baseline),
        scenario=_serialize_comparison(result.scenario),
        saving_old=str(result.saving_old),
        saving_new=str(result.saving_new),
    )


@router.get("/rules/supported", response_model=list[str])
async def get_supported_fys(user: CurrentUser):  # noqa: ARG001
    return _supported_fys()


@router.get(
    "/reconciliation/{financial_year}",
    response_model=ReconciliationBundleResponse,
)
async def get_reconciliation_bundle(
    financial_year: str,
    user: CurrentUser,
    db: DbSession,
):
    """Run AIS / 26AS / Form-16 reconciliation against the user's ledger.

    Returns one report per source. Each report lists matched, missing-in-
    ledger, missing-in-portal, and amount-mismatch lines so the UI can drive
    the missing-document checklist + reconciliation table.
    """
    try:
        reports = await run_all_reconciliations(db, user.id, financial_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ReconciliationBundleResponse(
        fy=financial_year,
        reports=[
            ReconciliationReportResponse(
                fy=report.fy,
                source=report.source,
                matched=report.matched,
                missing_in_ledger=report.missing_in_ledger,
                missing_in_portal=report.missing_in_portal,
                amount_mismatch=report.amount_mismatch,
                total_portal_amount=str(report.total_portal_amount),
                total_ledger_amount=str(report.total_ledger_amount),
                lines=[
                    ReconciliationLineResponse(
                        kind=line.kind,
                        label=line.label,
                        portal_amount=str(line.portal_amount)
                        if line.portal_amount is not None
                        else None,
                        ledger_amount=str(line.ledger_amount)
                        if line.ledger_amount is not None
                        else None,
                        delta=str(line.delta) if line.delta is not None else None,
                        portal_date=line.portal_date,
                        ledger_canonical_id=line.ledger_canonical_id,
                        notes=line.notes,
                    )
                    for line in report.lines
                ],
            )
            for report in reports
        ],
    )
