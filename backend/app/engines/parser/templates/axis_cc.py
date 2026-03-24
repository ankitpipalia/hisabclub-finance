"""Axis Bank Credit Card Statement Parser.

Handles Axis Bank credit card statement PDFs.
Statement format varies but typically has Date, Description, Amount columns.
Axis statements often have the card number and statement period on the first page.
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


class AxisCreditCardParser(StatementParser):
    _DATE_TOKEN = r"\d{1,2}(?:[/\-]\d{1,2}[/\-]\d{2,4}|[/\-]\w{3}[/\-]\d{2,4})"
    _TXN_WITH_CASHBACK_RE = re.compile(
        rf"^(?P<date>{_DATE_TOKEN})\s+"
        r"(?P<description>.+?)\s+"
        r"(?P<amount>[0-9][0-9,]*\.\d{2})\s+"
        r"(?P<drcr>Cr|Dr|CR|DR)\s+"
        r"[0-9][0-9,]*\.\d{2}\s+(?:Cr|Dr|CR|DR)\s*$"
    )
    _TXN_SINGLE_AMOUNT_RE = re.compile(
        rf"^(?P<date>{_DATE_TOKEN})\s+"
        r"(?P<description>.+?)\s+"
        r"(?P<amount>[0-9][0-9,]*\.\d{2})\s+"
        r"(?P<drcr>Cr|Dr|CR|DR)\s*$"
    )

    @property
    def parser_id(self) -> str:
        return "axis_cc_v1"

    @property
    def bank_name(self) -> str:
        return "AXIS"

    @property
    def account_type(self) -> str:
        return "credit_card"

    def detect(self, text: str) -> bool:
        has_axis = bool(re.search(r"Axis\s*Bank", text, re.IGNORECASE))
        has_cc = bool(
            re.search(r"Credit\s*Card|Card\s*Statement|Card\s*Number", text, re.IGNORECASE)
        )
        not_savings = not bool(
            re.search(r"Savings\s*Account|Current\s*Account", text, re.IGNORECASE)
        )
        return has_axis and has_cc and not_savings

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
        lines = text.splitlines()
        top_lines = lines[:150]
        top_text = "\n".join(top_lines)

        # Card number
        m = re.search(
            r"Card\s*(?:Number|No\.?|#)\s*[:\-]?\s*([\dXx\*\s]{12,19})",
            top_text,
            re.IGNORECASE,
        )
        if not m:
            m = re.search(r"\b(\d{6}\*{2,}\d{4})\b", top_text)
        if m:
            raw = re.sub(r"\s", "", m.group(1))
            stmt.account_number_masked = f"XXXX XXXX XXXX {raw[-4:]}" if len(raw) >= 4 else raw

        # Newer Axis layout: summary values are on the line after the header row.
        for idx, line in enumerate(top_lines):
            upper = line.upper()
            if "TOTAL PAYMENT DUE" in upper and "MINIMUM PAYMENT DUE" in upper:
                for off in range(1, 4):
                    if idx + off >= len(top_lines):
                        break
                    candidate = top_lines[idx + off]
                    m = re.search(
                        r"([0-9][0-9,]*\.\d{2})\s*(?:Cr|Dr|CR|DR)?\s+"
                        r"([0-9][0-9,]*\.\d{2})\s*(?:Cr|Dr|CR|DR)?\s+"
                        r"(\d{1,2}/\d{1,2}/\d{2,4})\s*[-–]\s*"
                        r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"
                        r"(\d{1,2}/\d{1,2}/\d{2,4})",
                        candidate,
                        re.IGNORECASE,
                    )
                    if not m:
                        continue
                    stmt.total_amount_due = parse_indian_amount(m.group(1))
                    stmt.min_amount_due = parse_indian_amount(m.group(2))
                    stmt.statement_period_start = parse_indian_date(m.group(3))
                    stmt.statement_period_end = parse_indian_date(m.group(4))
                    stmt.due_date = parse_indian_date(m.group(5))
                    break
                break

        # Credit limits are usually in the line below this heading.
        for idx, line in enumerate(top_lines):
            upper = line.upper()
            if "CREDIT CARD NUMBER" not in upper or "CREDIT LIMIT" not in upper:
                continue

            for off in range(1, 4):
                if idx + off >= len(top_lines):
                    break
                candidate = top_lines[idx + off]
                m = re.search(
                    r"(\d{6}\*{2,}\d{4})\s+"
                    r"([0-9][0-9,]*\.\d{2})\s+"
                    r"([0-9][0-9,]*\.\d{2})",
                    candidate,
                )
                if not m:
                    continue

                if stmt.account_number_masked is None:
                    raw = m.group(1)
                    stmt.account_number_masked = f"XXXX XXXX XXXX {raw[-4:]}"
                stmt.credit_limit = parse_indian_amount(m.group(2))
                stmt.available_limit = parse_indian_amount(m.group(3))
                break
            break

    def _extract_transactions(
        self, pages: list[str], full_text: str, stmt: ExtractedStatement
    ) -> None:
        lines = full_text.split("\n")
        transactions: list[ExtractedTransaction] = []
        pending_continuation: ExtractedTransaction | None = None

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                pending_continuation = None
                continue

            match = self._TXN_WITH_CASHBACK_RE.match(stripped)
            if not match:
                match = self._TXN_SINGLE_AMOUNT_RE.match(stripped)

            if match:
                txn_date = parse_indian_date(match.group("date"))
                if not txn_date:
                    pending_continuation = None
                    continue

                amount = parse_indian_amount(match.group("amount"))
                if amount is None or amount == 0:
                    pending_continuation = None
                    continue

                description = re.sub(r"\s{2,}", " ", match.group("description").strip())
                dr_cr = match.group("drcr").upper()
                direction = "credit" if dr_cr == "CR" else "debit"

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
                continue

            # Rare wrapped descriptions: append one continuation line only.
            if pending_continuation and not re.match(self._DATE_TOKEN, stripped):
                if "END OF STATEMENT" in stripped.upper():
                    pending_continuation = None
                    continue
                pending_continuation.description += " " + stripped
                pending_continuation = None

        stmt.transactions = transactions


register_parser(AxisCreditCardParser())
