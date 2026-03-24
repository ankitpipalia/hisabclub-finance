"""SBI Credit Card Statement Parser.

Handles SBI Card credit card statement PDFs.
SBI Card statements (issued by SBI Card, not SBI bank) have a distinct format
with Date, Transaction Details, Amount columns.
"""

from __future__ import annotations

import re

from app.engines.parser.amount_utils import parse_indian_amount, parse_indian_date
from app.engines.parser.base import (
    ExtractedStatement,
    ExtractedTransaction,
    StatementParser,
    register_parser,
)


class SbiCreditCardParser(StatementParser):
    @property
    def parser_id(self) -> str:
        return "sbi_cc_v1"

    @property
    def bank_name(self) -> str:
        return "SBI"

    @property
    def account_type(self) -> str:
        return "credit_card"

    def detect(self, text: str) -> bool:
        # SBI Card statements say "SBI Card" (the entity is SBI Cards & Payment Services)
        has_sbi = bool(
            re.search(r"SBI\s*Card|State\s*Bank.*?Credit\s*Card", text, re.IGNORECASE)
        )
        has_statement = bool(
            re.search(r"Statement|Card\s*Statement|Account\s*Summary", text, re.IGNORECASE)
        )
        not_savings = not bool(
            re.search(r"Savings\s*Account|Current\s*Account|Passbook", text, re.IGNORECASE)
        )
        return has_sbi and has_statement and not_savings

    def parse(self, pages: list[str], full_text: str) -> ExtractedStatement:
        stmt = ExtractedStatement(
            bank_name=self.bank_name,
            account_type=self.account_type,
            parser_id=self.parser_id,
        )

        self._extract_metadata(full_text, stmt)
        self._extract_transactions(pages, full_text, stmt)

        return stmt

    def _extract_metadata(self, text: str, stmt: ExtractedStatement) -> None:
        # Card number — SBI Card often shows "Card No: XXXX XXXX XXXX 1234"
        m = re.search(
            r"Card\s*(?:Number|No\.?|#)\s*[:\-]?\s*([\dXx\*\s]{12,19})", text, re.IGNORECASE
        )
        if m:
            raw = re.sub(r"\s", "", m.group(1))
            stmt.account_number_masked = f"XXXX XXXX XXXX {raw[-4:]}" if len(raw) >= 4 else raw

        # Statement period
        m = re.search(
            r"Statement\s*(?:Period|Date)\s*[:\-]?\s*"
            r"(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4})\s*(?:to|-)\s*"
            r"(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4})",
            text,
            re.IGNORECASE,
        )
        if not m:
            m = re.search(
                r"(?:Period|From)\s*[:\-]?\s*"
                r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|-)\s*"
                r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
                text,
                re.IGNORECASE,
            )
        if m:
            stmt.statement_period_start = parse_indian_date(m.group(1))
            stmt.statement_period_end = parse_indian_date(m.group(2))

        # Total due
        m = re.search(
            r"Total\s*(?:Amount\s*)?(?:Due|Payable|Outstanding)\s*[:\-]?\s*"
            r"(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.total_amount_due = parse_indian_amount(m.group(1))

        # Minimum due
        m = re.search(
            r"Min(?:imum)?\s*(?:Amount\s*)?Due\s*[:\-]?\s*"
            r"(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.min_amount_due = parse_indian_amount(m.group(1))

        # Due date
        m = re.search(
            r"(?:Payment\s*)?Due\s*Date\s*[:\-]?\s*"
            r"(\d{1,2}[/\-.\s]\w{3,9}[/\-.\s]\d{2,4}|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.due_date = parse_indian_date(m.group(1))

        # Credit limit
        m = re.search(
            r"(?:Total\s*)?Credit\s*Limit\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.credit_limit = parse_indian_amount(m.group(1))

        # Previous balance / Opening balance
        m = re.search(
            r"(?:Previous|Opening)\s*Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.previous_balance = parse_indian_amount(m.group(1))

    def _extract_transactions(
        self, pages: list[str], full_text: str, stmt: ExtractedStatement
    ) -> None:
        lines = full_text.split("\n")
        transactions: list[ExtractedTransaction] = []
        in_section = False

        # SBI Card transaction patterns:
        # DD MMM YY  MERCHANT NAME  1,234.56 [Cr]
        # DD/MM/YYYY  MERCHANT NAME  1,234.56
        txn_pattern = re.compile(
            r"^(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4}|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"
            r"(.+?)\s+"
            r"([\d,]+\.?\d{2})"
            r"(?:\s*(Cr|Dr|CR|DR|C|D))?\s*$"
        )

        section_starts = [
            re.compile(r"Transaction\s*Detail", re.IGNORECASE),
            re.compile(r"Date\s+(?:Transaction|Particular|Description|Narration)", re.IGNORECASE),
            re.compile(r"Domestic\s*Transaction", re.IGNORECASE),
            re.compile(r"New\s*Transaction", re.IGNORECASE),
        ]

        section_ends = [
            re.compile(r"Total\s*(?:Due|Amount|New\s*Transaction)", re.IGNORECASE),
            re.compile(r"Reward\s*(?:Point|Summary)", re.IGNORECASE),
            re.compile(r"Terms\s*(?:and|&)\s*Condition", re.IGNORECASE),
            re.compile(r"(?:Note|Disclaimer)\s*:", re.IGNORECASE),
            re.compile(r"Account\s*Summary", re.IGNORECASE),
        ]

        skip_patterns = [
            re.compile(r"^Date\s+", re.IGNORECASE),
            re.compile(r"Page\s*\d+", re.IGNORECASE),
            re.compile(r"^-{3,}$"),
            re.compile(r"SBI\s*Card", re.IGNORECASE),
        ]

        pending_continuation = None

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                if in_section and transactions:
                    in_section = False
                continue

            if not in_section:
                for sp in section_starts:
                    if sp.search(stripped):
                        in_section = True
                        break
                continue

            if any(ep.search(stripped) for ep in section_ends):
                in_section = False
                continue

            if any(sp.search(stripped) for sp in skip_patterns):
                continue

            m = txn_pattern.match(stripped)
            if m:
                txn_date = parse_indian_date(m.group(1))
                if not txn_date:
                    continue

                description = m.group(2).strip()
                amount = parse_indian_amount(m.group(3))
                cr_dr = m.group(4)

                if not amount or amount == 0:
                    continue

                direction = "credit" if cr_dr and cr_dr.upper() in ("CR", "C") else "debit"

                txn = ExtractedTransaction(
                    transaction_date=txn_date,
                    posting_date=None,
                    description=description,
                    amount=amount,
                    direction=direction,
                    line_number=line_num,
                )
                transactions.append(txn)
                pending_continuation = txn
            elif pending_continuation and stripped and not stripped[0].isdigit():
                pending_continuation.description += " " + stripped
                pending_continuation = None

        stmt.transactions = transactions


register_parser(SbiCreditCardParser())
