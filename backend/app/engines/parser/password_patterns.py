from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.parser.hints import normalize_bank_hint
from app.engines.parser.pdf_utils import decrypt_pdf
from app.models.institution_password_pattern import InstitutionPasswordPattern


@dataclass
class PdfPasswordResolution:
    password: str | None
    encrypted: bool
    source: str
    attempted: int
    manual_password_rejected: bool = False


async def resolve_pdf_password(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    pdf_content: bytes,
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
    source_filename: str | None = None,
    manual_password: str | None = None,
) -> PdfPasswordResolution:
    if _can_open_without_password(pdf_content):
        return PdfPasswordResolution(
            password=None,
            encrypted=False,
            source="not_encrypted",
            attempted=0,
        )

    attempted = 0
    manual_rejected = False
    if manual_password:
        attempted += 1
        if _can_open_with_password(pdf_content, manual_password):
            return PdfPasswordResolution(
                password=manual_password,
                encrypted=True,
                source="manual",
                attempted=attempted,
            )
        manual_rejected = True

    bank_code = normalize_bank_hint(bank_hint) or _infer_bank_code_from_filename(source_filename)
    scopes = _candidate_scopes(account_type_hint)
    query = (
        select(InstitutionPasswordPattern)
        .where(
            InstitutionPasswordPattern.user_id == user_id,
            InstitutionPasswordPattern.is_active == True,  # noqa: E712
        )
        .where(InstitutionPasswordPattern.account_scope.in_(scopes))
        .order_by(
            InstitutionPasswordPattern.account_scope.desc(),
            InstitutionPasswordPattern.updated_at.desc(),
        )
    )
    if bank_code:
        query = query.where(
            or_(
                InstitutionPasswordPattern.bank_code == bank_code,
                InstitutionPasswordPattern.bank_code == "ANY",
            )
        )
    rows = (await db.execute(query)).scalars().all()

    context = _build_context(
        bank_code=bank_code,
        account_type_hint=account_type_hint,
        source_filename=source_filename,
    )
    seen: set[str] = set()
    for pattern in rows:
        candidates = _render_candidates(pattern=pattern, context=context)
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            attempted += 1
            if _can_open_with_password(pdf_content, candidate):
                return PdfPasswordResolution(
                    password=candidate,
                    encrypted=True,
                    source=f"pattern:{pattern.id}",
                    attempted=attempted,
                    manual_password_rejected=manual_rejected,
                )

    return PdfPasswordResolution(
        password=None,
        encrypted=True,
        source="unresolved",
        attempted=attempted,
        manual_password_rejected=manual_rejected,
    )


def _candidate_scopes(account_type_hint: str | None) -> list[str]:
    normalized = (account_type_hint or "").strip().lower()
    if normalized == "credit_card":
        return ["credit_card", "any"]
    if normalized in {"bank_account", "savings", "current"}:
        return ["bank_account", "any"]
    return ["any", "bank_account", "credit_card"]


def _build_context(
    *,
    bank_code: str | None,
    account_type_hint: str | None,
    source_filename: str | None,
) -> dict[str, str]:
    stem = ""
    if source_filename:
        stem = source_filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    cleaned_stem = re.sub(r"[^A-Za-z0-9]", "", stem)
    return {
        "bank_code": (bank_code or "").upper(),
        "account_type": (account_type_hint or "").lower(),
        "file_stem": stem,
        "file_stem_upper": cleaned_stem.upper(),
        "file_stem_lower": cleaned_stem.lower(),
    }


def _render_candidates(
    *,
    pattern: InstitutionPasswordPattern,
    context: dict[str, str],
) -> list[str]:
    variables = dict(pattern.variables_json or {})
    formatted_context = {**context, **{str(k): str(v) for k, v in variables.items()}}
    template = (pattern.pattern_template or "").strip()
    if not template:
        return []

    if (pattern.pattern_type or "").lower() == "static_password":
        base = template
    else:
        base = _safe_format_template(template, formatted_context)
        if base is None:
            return []

    variants = [base.strip(), base.strip().upper(), base.strip().lower()]
    return [candidate for candidate in variants if candidate]


def _safe_format_template(template: str, values: dict[str, str]) -> str | None:
    rendered = template
    for key in re.findall(r"{([a-zA-Z0-9_]+)}", template):
        if key not in values:
            return None
        rendered = rendered.replace(f"{{{key}}}", str(values[key]))
    return rendered


def _infer_bank_code_from_filename(source_filename: str | None) -> str | None:
    if not source_filename:
        return None
    return normalize_bank_hint(source_filename)


def _can_open_without_password(pdf_content: bytes) -> bool:
    try:
        decrypt_pdf(pdf_content, None)
        return True
    except ValueError:
        return False


def _can_open_with_password(pdf_content: bytes, password: str) -> bool:
    try:
        decrypt_pdf(pdf_content, password)
        return True
    except ValueError:
        return False
