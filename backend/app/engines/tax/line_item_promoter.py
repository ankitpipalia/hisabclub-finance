"""Idempotent persistence of parser-emitted `lines` into the new tables.

Called from `api/v1/tax.py:upload_portal_document` right after the
`TaxPortalData` row is flushed. Failing to persist a line is non-fatal —
we log and skip; the aggregate `extracted_json` payload is still saved.

Idempotency contract: re-uploading the same Form-16 / 26AS / AIS should NOT
duplicate rows. We use a deterministic key per table (see migration
`phase35_tax_line_items.py`).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_line_items import (
    AisLineItem,
    Form16Item,
    Form26AsLineItem,
)

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


async def _ais_already_present(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    fy: str,
    category: str,
    amount: Decimal,
    info_source: str | None,
) -> bool:
    stmt = select(AisLineItem.id).where(
        AisLineItem.user_id == user_id,
        AisLineItem.fy == fy,
        AisLineItem.category == category,
        AisLineItem.amount == amount,
    )
    if info_source is not None:
        stmt = stmt.where(AisLineItem.info_source == info_source)
    row = (await db.execute(stmt.limit(1))).first()
    return row is not None


async def _form26as_already_present(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    fy: str,
    part: str,
    deductor_tan: str | None,
    section: str | None,
    amount_tds: Decimal | None,
    amount_credit: Decimal | None,
) -> bool:
    stmt = select(Form26AsLineItem.id).where(
        Form26AsLineItem.user_id == user_id,
        Form26AsLineItem.fy == fy,
        Form26AsLineItem.part == part,
    )
    if deductor_tan is not None:
        stmt = stmt.where(Form26AsLineItem.deductor_tan == deductor_tan)
    if section is not None:
        stmt = stmt.where(Form26AsLineItem.section == section)
    if amount_tds is not None:
        stmt = stmt.where(Form26AsLineItem.amount_tds == amount_tds)
    if amount_credit is not None:
        stmt = stmt.where(Form26AsLineItem.amount_credit == amount_credit)
    row = (await db.execute(stmt.limit(1))).first()
    return row is not None


async def _form16_already_present(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    fy: str,
    employer_tan: str | None,
    head: str,
) -> bool:
    stmt = select(Form16Item.id).where(
        Form16Item.user_id == user_id,
        Form16Item.fy == fy,
        Form16Item.head == head,
    )
    if employer_tan is not None:
        stmt = stmt.where(Form16Item.employer_tan == employer_tan)
    row = (await db.execute(stmt.limit(1))).first()
    return row is not None


async def promote_line_items(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    fy: str,
    doc_artifact_id: uuid.UUID | None,
    parsed: dict,
) -> dict[str, int]:
    """Persist the parser's `lines` array into the appropriate table.

    `parsed` is the dict emitted by ais/form_26as/form16_parser. The
    `document_type` key drives table selection.

    Returns counters for caller logging.
    """
    counts = {"inserted": 0, "skipped_duplicate": 0, "skipped_invalid": 0}
    doc_type = (parsed.get("document_type") or "").lower()
    lines = parsed.get("lines") or []
    if not isinstance(lines, list) or not lines:
        return counts

    for line in lines:
        if not isinstance(line, dict):
            counts["skipped_invalid"] += 1
            continue

        if doc_type == "form_16":
            head = line.get("head")
            amount = _to_decimal(line.get("amount"))
            if not head or amount is None or amount <= 0:
                counts["skipped_invalid"] += 1
                continue
            employer_tan = (parsed.get("employer_tan") or None)
            if await _form16_already_present(
                db,
                user_id=user_id,
                fy=fy,
                employer_tan=employer_tan,
                head=head,
            ):
                counts["skipped_duplicate"] += 1
                continue
            db.add(
                Form16Item(
                    user_id=user_id,
                    fy=fy,
                    employer_name=parsed.get("employer_name"),
                    employer_tan=employer_tan,
                    head=head,
                    amount=amount,
                    evidence_doc_artifact_id=doc_artifact_id,
                    raw_row=line,
                )
            )
            counts["inserted"] += 1

        elif doc_type == "form_26as":
            part = line.get("part") or "A"
            amount_tds = _to_decimal(line.get("amount_tds"))
            amount_credit = _to_decimal(line.get("amount_credit"))
            if amount_tds is None and amount_credit is None:
                counts["skipped_invalid"] += 1
                continue
            deductor_tan = line.get("deductor_tan")
            section = line.get("section")
            if await _form26as_already_present(
                db,
                user_id=user_id,
                fy=fy,
                part=part,
                deductor_tan=deductor_tan,
                section=section,
                amount_tds=amount_tds,
                amount_credit=amount_credit,
            ):
                counts["skipped_duplicate"] += 1
                continue
            db.add(
                Form26AsLineItem(
                    user_id=user_id,
                    fy=fy,
                    part=part,
                    deductor_tan=deductor_tan,
                    deductor_name=line.get("deductor_name"),
                    section=section,
                    amount_credit=amount_credit,
                    amount_tds=amount_tds,
                    evidence_doc_artifact_id=doc_artifact_id,
                    raw_row=line,
                )
            )
            counts["inserted"] += 1

        elif doc_type in {"ais", "tis"}:
            category = line.get("category")
            amount = _to_decimal(line.get("amount"))
            if not category or amount is None or amount <= 0:
                counts["skipped_invalid"] += 1
                continue
            info_source = line.get("info_source")
            if await _ais_already_present(
                db,
                user_id=user_id,
                fy=fy,
                category=category,
                amount=amount,
                info_source=info_source,
            ):
                counts["skipped_duplicate"] += 1
                continue
            db.add(
                AisLineItem(
                    user_id=user_id,
                    fy=fy,
                    category=category,
                    sub_category=line.get("sub_category"),
                    deductor_name=line.get("deductor_name"),
                    deductor_pan=line.get("deductor_pan"),
                    amount=amount,
                    info_source=info_source,
                    evidence_doc_artifact_id=doc_artifact_id,
                    raw_row=line,
                )
            )
            counts["inserted"] += 1
        else:
            counts["skipped_invalid"] += 1

    await db.flush()
    logger.info(
        "Line-item promotion: doc_type=%s user=%s fy=%s counts=%s",
        doc_type,
        user_id,
        fy,
        counts,
    )
    return counts
