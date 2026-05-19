"""CA export pack — Sprint B.5.

`build_ca_pack(db, user_id, fy) -> bytes` produces a ZIP a user can hand to
their CA. Contents:

  - summary.md       — plain-text one-pager covering income, deductions, regime
                       comparison, tax payable, refund/demand, assumptions
  - ledger_FY.csv    — every canonical transaction in the FY (PII included;
                       this file is intended for the CA, not for sharing)
  - regime_comparison.json
  - deduction_breakup.csv
  - reconciliation_FY.csv
  - documents.csv    — index of document_artifacts (filename, doc_type, hash)
  - assumptions.md   — regime notes + checklist gaps + non-modelled scenarios

We use only stdlib `zipfile` + `csv` + `json` so no extra dependencies are
required. A future revision can swap `summary.md` for `summary.pdf` via
reportlab.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.tax.checklist import build_checklist
from app.engines.tax.deductions import compute_utilization
from app.engines.tax.reconcile.wire import _fy_window, run_all_reconciliations
from app.engines.tax.regime import TaxInputs, compare
from app.engines.tax.rules import get_rules
from app.models.canonical_transaction import CanonicalTransaction
from app.models.document_artifact import DocumentArtifact
from app.models.tax_line_items import (
    AisLineItem,
    Form16Item,
    Form26AsLineItem,
    TaxReconciliationMatch,
)


@dataclass(frozen=True)
class CaPack:
    fy: str
    content: bytes
    filename: str


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


async def _ledger_for_fy(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[CanonicalTransaction]:
    rows = (
        await db.execute(
            select(CanonicalTransaction).where(
                CanonicalTransaction.user_id == user_id,
                CanonicalTransaction.transaction_date >= start,
                CanonicalTransaction.transaction_date <= end,
                CanonicalTransaction.is_excluded == False,  # noqa: E712
            ).order_by(CanonicalTransaction.transaction_date.asc())
        )
    ).scalars().all()
    return list(rows)


async def _document_index(
    db: AsyncSession, user_id: uuid.UUID
) -> list[DocumentArtifact]:
    rows = (
        await db.execute(
            select(DocumentArtifact)
            .where(DocumentArtifact.user_id == user_id)
            .order_by(DocumentArtifact.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def _matches_for(
    db: AsyncSession, user_id: uuid.UUID
) -> list[TaxReconciliationMatch]:
    rows = (
        await db.execute(
            select(TaxReconciliationMatch).where(
                TaxReconciliationMatch.user_id == user_id
            )
        )
    ).scalars().all()
    return list(rows)


def _form16_to_tax_inputs(
    f16_items: list[Form16Item],
) -> TaxInputs:
    by_head = {item.head: item.amount for item in f16_items}
    return TaxInputs(
        gross_salary=by_head.get("gross_salary", Decimal("0")),
        is_salaried=bool(by_head.get("gross_salary")),
        deduction_80c=min(by_head.get("deduction_80c", Decimal("0")), Decimal("150000")),
        deduction_80d_self=by_head.get("deduction_80d", Decimal("0")),
        deduction_80ccd_1b=by_head.get("deduction_80ccd_1b", Decimal("0")),
    )


async def build_ca_pack(
    db: AsyncSession, user_id: uuid.UUID, fy: str
) -> CaPack:
    """Generate the CA hand-off ZIP for the given user + FY.

    Caller is responsible for HTTP streaming. Returned `bytes` is the
    complete ZIP payload.
    """
    rules = get_rules(fy)  # validates fy; raises ValueError on bad input
    start, end = _fy_window(fy)

    # ---- Gather data ----
    txns = await _ledger_for_fy(db, user_id, start, end)
    artifacts = await _document_index(db, user_id)
    matches = await _matches_for(db, user_id)
    reports = await run_all_reconciliations(db, user_id, fy)
    checklist = await build_checklist(db, user_id, fy)

    f16_items = (
        await db.execute(
            select(Form16Item).where(
                Form16Item.user_id == user_id, Form16Item.fy == fy
            )
        )
    ).scalars().all()
    f26_items = (
        await db.execute(
            select(Form26AsLineItem).where(
                Form26AsLineItem.user_id == user_id, Form26AsLineItem.fy == fy
            )
        )
    ).scalars().all()
    ais_items = (
        await db.execute(
            select(AisLineItem).where(
                AisLineItem.user_id == user_id, AisLineItem.fy == fy
            )
        )
    ).scalars().all()

    tax_inputs = _form16_to_tax_inputs(list(f16_items))
    comparison = compare(fy, tax_inputs)
    deduction_report = compute_utilization(
        fy,
        {
            "deduction_80c": tax_inputs.deduction_80c,
            "deduction_80ccd_1b": tax_inputs.deduction_80ccd_1b,
            "deduction_80d_self": tax_inputs.deduction_80d_self,
        },
    )

    # ---- Build ZIP in-memory ----
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.md", _build_summary_md(fy, comparison, checklist, txns))
        zf.writestr("ledger_FY.csv", _build_ledger_csv(txns))
        zf.writestr(
            "regime_comparison.json",
            json.dumps(
                {
                    "fy": comparison.fy,
                    "recommendation": comparison.recommendation,
                    "delta": str(comparison.delta),
                    "old": _result_to_dict(comparison.old),
                    "new": _result_to_dict(comparison.new),
                    "sources": list(rules.sources),
                },
                indent=2,
            ),
        )
        zf.writestr("deduction_breakup.csv", _build_deduction_csv(deduction_report))
        zf.writestr("reconciliation_FY.csv", _build_reconciliation_csv(reports, matches))
        zf.writestr("documents.csv", _build_documents_csv(artifacts))
        zf.writestr(
            "assumptions.md",
            _build_assumptions_md(comparison, checklist, ais_items, f26_items, f16_items),
        )

    buf.seek(0)
    return CaPack(
        fy=fy,
        content=buf.getvalue(),
        filename=f"hisabclub_capack_{fy}.zip",
    )


def _result_to_dict(result) -> dict:
    return {
        "regime": result.regime,
        "total_tax": str(result.total_tax),
        "taxable_income": str(result.taxable_income),
        "tax_on_slabs": str(result.tax_on_slabs),
        "rebate_87a": str(result.rebate_87a),
        "surcharge": str(result.surcharge),
        "cess": str(result.cess),
        "notes": list(result.notes),
    }


def _build_summary_md(fy, comparison, checklist, txns) -> str:
    rec = comparison.recommendation
    lines = [
        f"# HisabClub CA Hand-off — FY {fy}",
        "",
        f"_Generated: {datetime.utcnow().isoformat()}Z_",
        "",
        "## Headline numbers",
        "",
        f"- **Recommended regime:** {rec}",
        f"- **Total tax (old regime):** ₹{comparison.old.total_tax}",
        f"- **Total tax (new regime):** ₹{comparison.new.total_tax}",
        f"- **Savings:** ₹{abs(comparison.delta)} under the {rec} regime",
        f"- **Canonical transactions in FY:** {len(txns)}",
        "",
        "## Checklist",
        "",
    ]
    for item in checklist.items:
        lines.append(f"- **{item.severity.upper()}** — {item.title}: {item.detail}")
    if not checklist.items:
        lines.append("- All checked items are present.")
    lines.append("")
    lines.append("## Files in this pack")
    lines.append("")
    lines.append("- `ledger_FY.csv` — every transaction in the FY")
    lines.append("- `regime_comparison.json` — old vs new full breakdown")
    lines.append("- `deduction_breakup.csv` — Sec 80x claims and remaining caps")
    lines.append("- `reconciliation_FY.csv` — AIS / 26AS / Form-16 matches")
    lines.append("- `documents.csv` — index of supporting docs")
    lines.append("- `assumptions.md` — non-modelled scenarios + rule basis")
    return "\n".join(lines)


def _build_ledger_csv(txns: list[CanonicalTransaction]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "id",
            "transaction_date",
            "amount",
            "direction",
            "transaction_nature",
            "merchant_raw",
            "category_id",
            "bank_name",
            "account_masked",
            "extraction_source",
            "validation_status",
            "source_statement_id",
        ]
    )
    for t in txns:
        writer.writerow(
            [
                _stringify(t.id),
                _stringify(t.transaction_date),
                _stringify(t.amount),
                _stringify(t.direction),
                _stringify(t.transaction_nature),
                _stringify(t.merchant_raw),
                _stringify(t.category_id),
                _stringify(t.bank_name),
                _stringify(t.account_masked),
                _stringify(t.extraction_source),
                _stringify(t.validation_status),
                _stringify(t.source_statement_id),
            ]
        )
    return out.getvalue()


def _build_deduction_csv(report) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["section", "cap", "claimed", "remaining", "description"])
    for item in report.items:
        writer.writerow(
            [
                item.section,
                _stringify(item.cap),
                _stringify(item.claimed),
                _stringify(item.remaining),
                item.description,
            ]
        )
    return out.getvalue()


def _build_reconciliation_csv(reports, matches) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "source",
            "kind",
            "label",
            "portal_amount",
            "ledger_amount",
            "delta",
            "notes",
        ]
    )
    for report in reports:
        for line in report.lines:
            writer.writerow(
                [
                    report.source,
                    line.kind,
                    line.label,
                    _stringify(line.portal_amount),
                    _stringify(line.ledger_amount),
                    _stringify(line.delta),
                    line.notes,
                ]
            )
    if matches:
        writer.writerow([])
        writer.writerow(
            [
                "matches_below",
                "source_table",
                "source_row_id",
                "canonical_transaction_id",
                "match_score",
                "match_kind",
                "matched_by",
            ]
        )
        for m in matches:
            writer.writerow(
                [
                    "",
                    m.source_table,
                    _stringify(m.source_row_id),
                    _stringify(m.canonical_transaction_id),
                    _stringify(m.match_score),
                    m.match_kind or "",
                    m.matched_by,
                ]
            )
    return out.getvalue()


def _build_documents_csv(artifacts: list[DocumentArtifact]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "id",
            "file_name",
            "file_ext",
            "doc_type",
            "file_hash_sha256",
            "created_at",
        ]
    )
    for a in artifacts:
        writer.writerow(
            [
                _stringify(a.id),
                a.file_name,
                a.file_ext,
                _stringify(getattr(a, "doc_type", "")),
                a.file_hash_sha256,
                _stringify(a.created_at),
            ]
        )
    return out.getvalue()


def _build_assumptions_md(comparison, checklist, ais_items, f26_items, f16_items) -> str:
    lines = [
        "# Assumptions and non-modelled scenarios",
        "",
        "## Rule basis",
    ]
    for note in comparison.old.notes + comparison.new.notes:
        lines.append(f"- {note}")
    lines.append("")
    lines.append("## Non-modelled scenarios")
    lines.append("- Capital gains workbench (broker P&L parser) is on the Sprint D candidate list.")
    lines.append(
        "- Family-floater 80D split across self / parents senior age "
        "stratification is conservatively capped at higher limit."
    )
    lines.append(
        "- HRA exemption is NOT automatically deducted from gross_salary; "
        "provide it via `RegimeInputs.deduction_80gg` or HRA helper output."
    )
    lines.append("")
    lines.append("## Source coverage")
    lines.append(f"- AIS line items: {len(ais_items)}")
    lines.append(f"- 26AS line items: {len(f26_items)}")
    lines.append(f"- Form-16 items: {len(f16_items)}")
    lines.append("")
    if checklist.items:
        lines.append("## Open items the CA should be aware of")
        for item in checklist.items:
            if item.severity == "block_filing":
                lines.append(f"- 🛑 {item.title}: {item.detail}")
            elif item.severity == "warning":
                lines.append(f"- ⚠️ {item.title}: {item.detail}")
            else:
                lines.append(f"- ℹ️ {item.title}: {item.detail}")
    return "\n".join(lines)
