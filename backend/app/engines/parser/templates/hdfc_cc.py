"""HDFC Bank Credit Card Statement Parser.

Handles HDFC credit card statement PDFs (2020+ format).
Supports both older and newer (2025+) statement layouts.

Known formats:
- Domestic Transactions / International Transactions sections
- Date column: DD/MM/YYYY (newer may include "| HH:MM" timestamp)
- Description column: merchant name, city, reference numbers
- Amount column: Indian format (1,23,456.78), "Cr" suffix for credits
- Section terminators: "TOTAL AMOUNT", "Eligible for EMI", "Rewards Program",
  "Past Dues", "GST Summary", etc.
"""

from __future__ import annotations

import re
from datetime import timedelta

from app.engines.parser.amount_utils import parse_indian_amount, parse_indian_date
from app.engines.parser.base import (
    ExtractedStatement,
    ExtractedTransaction,
    StatementParser,
    register_parser,
)


def extract_hdfc_cc_period(text: str):
    """Extract HDFC CC billing period, with statement-date fallback.

    Some legacy HDFC PDFs only expose "Statement Date". In that case we use a
    deterministic 30-day billing window so downstream statement-period checks
    and dedup metadata are not left empty.
    """
    period_patterns = [
        # "Billing Period 18 Feb, 2026 - 17 Mar, 2026" (HDFC Swiggy card format)
        (
            r"Billing\s*Period\s*[:\-]?\s*"
            r"(\d{1,2}\s+\w{3,9},?\s+\d{4})\s*[\-–]\s*"
            r"(\d{1,2}\s+\w{3,9},?\s+\d{4})"
        ),
        # "Statement for the period 01 Dec 2024 to 31 Dec 2024"
        (
            r"Statement\s+for\s+(?:the\s+)?period\s*[:\-]?\s*"
            r"(\d{1,2}\s+\w{3,9},?\s+\d{4})\s*(?:to|-|–)\s*"
            r"(\d{1,2}\s+\w{3,9},?\s+\d{4})"
        ),
        # "Statement Period: 12/10/2024 to 11/11/2024"
        (
            r"Statement\s*Period\s*[:\-]?\s*"
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|-)\s*"
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
        ),
        # "Statement Period: 12 Oct 2024 to 11 Nov 2024"
        (
            r"(?:Statement|Billing)\s*Period\s*[:\-]?\s*"
            r"(\d{1,2}[\s/\-]\w{3,9}[\s,/\-]+\d{2,4})\s*(?:to|-|–)\s*"
            r"(\d{1,2}[\s/\-]\w{3,9}[\s,/\-]+\d{2,4})"
        ),
        # "From 12/10/2024 To 11/11/2024"
        (
            r"(?:From|Period)\s*[:\-]?\s*"
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|To|-)\s*"
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
        ),
    ]

    for pattern in period_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        start = parse_indian_date(match.group(1))
        end = parse_indian_date(match.group(2))
        if start and end:
            return start, end

    match = re.search(
        r"Statement\s*Date\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if match:
        end = parse_indian_date(match.group(1))
        if end:
            return end - timedelta(days=30), end

    return None, None


class HdfcCreditCardParser(StatementParser):
    _HDFC_BANK_RE = re.compile(r"\bHDFC\s+Bank\b", re.IGNORECASE)
    _CURRENCY_AMOUNT_RE = re.compile(
        r"(?:₹|INR|Rs\.?|C)\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )
    _DATE_VALUE_RE = re.compile(
        r"(\d{1,2}\s+\w{3,9},?\s+\d{4}|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
    )

    @property
    def parser_id(self) -> str:
        return "hdfc_cc_v1"

    @property
    def bank_name(self) -> str:
        return "HDFC"

    @property
    def account_type(self) -> str:
        return "credit_card"

    def detect(self, text: str) -> bool:
        indicators = [
            self._HDFC_BANK_RE.search(text),
            re.search(r"Credit\s*Card\s*Statement", text, re.IGNORECASE)
            or re.search(r"Card\s*Statement", text, re.IGNORECASE)
            or re.search(r"Domestic\s*Transactions", text, re.IGNORECASE)
            or re.search(r"Credit\s*Card", text, re.IGNORECASE),
        ]
        has_hdfc = indicators[0] is not None
        has_statement = indicators[1] is not None

        # Also check it's not a savings/debit statement
        is_savings = bool(
            re.search(r"Savings\s*Account|Current\s*Account", text, re.IGNORECASE)
        )

        return has_hdfc and has_statement and not is_savings

    def parse(self, pages: list[str], full_text: str) -> ExtractedStatement:
        stmt = ExtractedStatement(
            bank_name=self.bank_name,
            account_type=self.account_type,
            parser_id=self.parser_id,
        )

        self._extract_metadata(full_text, stmt)
        self._extract_transactions(pages, full_text, stmt)
        self._expand_period_to_transaction_range(stmt)

        return stmt

    # ── Metadata extraction ─────────────────────────────────

    def _extract_metadata(self, text: str, stmt: ExtractedStatement) -> None:
        # Account/Card number — various formats HDFC uses
        m = re.search(
            r"Card\s*(?:Number|No\.?|#)\s*[:\-]?\s*([\dXx\*\s]{12,19})",
            text,
            re.IGNORECASE,
        )
        if not m:
            # Some statements show card number as "5268 XXXX XXXX 1234"
            m = re.search(r"(\d{4}\s*[Xx\*]{4}\s*[Xx\*]{4}\s*\d{4})", text)
        if m:
            raw = re.sub(r"\s", "", m.group(1))
            stmt.account_number_masked = (
                f"XXXX XXXX XXXX {raw[-4:]}" if len(raw) >= 4 else raw
            )

        # Statement period — multiple HDFC date formats, plus statement-date fallback.
        stmt.statement_period_start, stmt.statement_period_end = extract_hdfc_cc_period(text)

        # Total amount due — HDFC uses "Total Amount Due" or "Total Dues"
        # Note: HDFC Swiggy card uses "C" prefix for currency (₹ extracted as C)
        for pat in [
            r"Total\s*(?:Amount\s*)?Due[s]?\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*|C\s*)?([\d,]+\.?\d*)",
            r"Total\s*Dues?\s*(?:Amount)?\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*|C\s*)?([\d,]+\.?\d*)",
            r"TOTAL\s*AMOUNT\s*DUE\s*[\n\r]*\s*(?:Rs\.?\s*|INR\s*|₹\s*|C\s*)?([\d,]+\.?\d*)",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                stmt.total_amount_due = parse_indian_amount(m.group(1))
                break

        # Minimum amount due
        m = re.search(
            r"Min(?:imum)?\s*(?:Amount\s*)?Due\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*|C\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.min_amount_due = parse_indian_amount(m.group(1))

        # Due date — handles "DUE DATE\n06 Apr, 2026" or "Due Date: 06/04/2026"
        for pat in [
            r"DUE\s*DATE\s*[\n\r]+\s*(?:C\s*)?([\d,]+\.?\d*)\s+(\d{1,2}\s+\w{3,9},?\s+\d{4})",
            r"(?:Payment\s*)?Due\s*Date\s*[:\-]?\s*(\d{1,2}\s+\w{3,9},?\s+\d{4})",
            r"(?:Payment\s*)?Due\s*Date\s*[:\-]?\s*(\d{1,2}[/\-.\s]\w{3,9}[/\-.\s]\d{2,4})",
            r"(?:Payment\s*)?Due\s*Date\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                # Some patterns have min_due before date
                date_str = m.group(m.lastindex)
                stmt.due_date = parse_indian_date(date_str)
                if stmt.due_date:
                    break

        # Credit limit
        m = re.search(
            r"(?:Total\s*)?Credit\s*Limit\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*|C\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.credit_limit = parse_indian_amount(m.group(1))

        # Available limit
        m = re.search(
            r"Available\s*(?:Credit\s*)?Limit\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*|C\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.available_limit = parse_indian_amount(m.group(1))

        # Previous balance / Opening balance
        m = re.search(
            r"(?:Previous|Opening|Last\s*Statement)\s*(?:.*?)Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.previous_balance = parse_indian_amount(m.group(1))

        # Payments received / Credits
        m = re.search(
            r"Payment[s]?\s*(?:Received|Credited|/Credits|/\s*Credits)\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.payments_received = parse_indian_amount(m.group(1))

        # Swiggy/HDFC table layout: labels and values are split across lines.
        self._extract_table_style_metadata(text, stmt)

    def _extract_table_style_metadata(self, text: str, stmt: ExtractedStatement) -> None:
        lines = text.splitlines()
        search_limit = min(len(lines), 140)

        for idx in range(search_limit):
            upper = lines[idx].upper()

            if stmt.total_amount_due is None and "TOTAL AMOUNT DUE" in upper:
                for off in range(1, 6):
                    if idx + off >= search_limit:
                        break
                    candidate = lines[idx + off]
                    if "RECEIVED" in candidate.upper():
                        continue
                    amounts = self._extract_currency_amounts(candidate)
                    if amounts:
                        stmt.total_amount_due = amounts[0]
                        break

            if (stmt.min_amount_due is None or stmt.due_date is None) and (
                "MINIMUM DUE" in upper and "DUE DATE" in upper
            ):
                for off in range(1, 6):
                    if idx + off >= search_limit:
                        break
                    candidate = lines[idx + off]
                    amounts = self._extract_currency_amounts(candidate)
                    if stmt.min_amount_due is None and amounts:
                        stmt.min_amount_due = amounts[0]

                    if stmt.due_date is None:
                        date_match = self._DATE_VALUE_RE.search(candidate)
                        if date_match:
                            parsed_date = parse_indian_date(date_match.group(1))
                            if parsed_date:
                                stmt.due_date = parsed_date

                    if stmt.min_amount_due is not None and stmt.due_date is not None:
                        break

            if (stmt.credit_limit is None or stmt.available_limit is None) and (
                "TOTAL CREDIT LIMIT" in upper
            ):
                for off in range(1, 7):
                    if idx + off >= search_limit:
                        break
                    amounts = self._extract_currency_amounts(lines[idx + off])
                    if len(amounts) < 2:
                        continue
                    if stmt.credit_limit is None:
                        stmt.credit_limit = amounts[0]
                    if stmt.available_limit is None:
                        stmt.available_limit = amounts[1]
                    break

    def _extract_currency_amounts(self, line: str) -> list[float]:
        amounts: list[float] = []
        for raw in self._CURRENCY_AMOUNT_RE.findall(line):
            parsed = parse_indian_amount(raw)
            if parsed is not None:
                amounts.append(parsed)
        return amounts

    def _expand_period_to_transaction_range(self, stmt: ExtractedStatement) -> None:
        if not stmt.transactions:
            return

        txn_dates = [txn.transaction_date for txn in stmt.transactions if txn.transaction_date]
        if not txn_dates:
            return

        first_txn_date = min(txn_dates)
        last_txn_date = max(txn_dates)
        if stmt.statement_period_start is None or first_txn_date < stmt.statement_period_start:
            stmt.statement_period_start = first_txn_date
        if stmt.statement_period_end is None or last_txn_date > stmt.statement_period_end:
            stmt.statement_period_end = last_txn_date

    # ── Transaction extraction ──────────────────────────────

    # Matches a date at the start of a line: DD/MM/YYYY, optionally followed by
    # "| HH:MM" or " HH:MM:SS" (newer HDFC Infinia format).
    _DATE_PREFIX = r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
    _OPTIONAL_TIME = r"(?:\s*\|?\s*\d{1,2}:\d{2}(?::\d{2})?)?"

    # Amount at end of line. HDFC uses multiple formats:
    # - "1,234.56" or "1,234.56 Cr"
    # - "C 1,234.56" or "C1,234.56" (C = currency symbol artifact from ₹)
    # - "+ C 1,234.56" (+ = credit indicator)
    # Capture groups: (1) credit indicator +, (2) amount digits, (3) Cr/Dr suffix
    _AMOUNT_SUFFIX = r"(\+)?\s*(?:C\s?)?([\d,]+\.\d{2})\s*(?:(Cr|Dr|CR|DR))?\s*(?:l)?"

    # Main transaction pattern:
    # DD/MM/YYYY [| HH:MM]  DESCRIPTION  [+] [C] AMOUNT [Cr] [l]
    _TXN_PATTERN = re.compile(
        rf"^\s*{_DATE_PREFIX}{_OPTIONAL_TIME}\s+"          # date [time]
        rf"(.+?)\s+"                                        # description (non-greedy)
        rf"{_AMOUNT_SUFFIX}\s*$"                            # [+] [C] amount [Cr/Dr] [l]
    )

    # Alternate: date + description only (amount might be on next line or table-split)
    _TXN_DATE_DESC = re.compile(
        rf"^\s*{_DATE_PREFIX}{_OPTIONAL_TIME}\s+(.+?)\s*$"
    )

    # Section start patterns — text that begins a transaction block
    _SECTION_STARTS = [
        re.compile(r"Domestic\s*Transactions?", re.IGNORECASE),
        re.compile(r"International\s*Transactions?", re.IGNORECASE),
        re.compile(r"Transaction\s*Details?", re.IGNORECASE),
        re.compile(
            r"Date\s+Transaction\s+(?:Description|Details?|Particulars?)",
            re.IGNORECASE,
        ),
        re.compile(r"Date\s+Particulars?\s+Amount", re.IGNORECASE),
        re.compile(r"Date\s+Description\s+Amount", re.IGNORECASE),
        re.compile(r"DATE\s*&\s*TIME\s+TRANSACTION\s+DESCRIPTION", re.IGNORECASE),
    ]

    # Section end / terminator patterns — text that ends a transaction block
    _SECTION_ENDS = [
        re.compile(r"TOTAL\s*AMOUNT", re.IGNORECASE),
        re.compile(r"Total\s*(?:Domestic|International)?\s*(?:Transaction|Amount)", re.IGNORECASE),
        re.compile(r"Eligible\s+for\s+(?:EMI|FlexiPay)", re.IGNORECASE),
        re.compile(r"CONVERT\s+TO\s+EMI", re.IGNORECASE),
        re.compile(r"Past\s*Dues?", re.IGNORECASE),
        re.compile(r"GST\s*Summary", re.IGNORECASE),
        re.compile(r"Rewards?\s*(?:Program|Point|Summary)", re.IGNORECASE),
        re.compile(r"Offers?\s+on\s+your\s+card", re.IGNORECASE),
        re.compile(r"Cash\s*Back\s*Summary", re.IGNORECASE),
        re.compile(r"Benefits\s+on\s+your\s+card", re.IGNORECASE),
        re.compile(r"Purchase\s+Indicator", re.IGNORECASE),
        re.compile(r"Terms\s*(?:and|&)\s*Condition", re.IGNORECASE),
        re.compile(r"Important\s*(?:Notice|Information)", re.IGNORECASE),
        re.compile(r"\*\s*Transaction\s+time", re.IGNORECASE),
        re.compile(r"^\s*TRANSACTIONS\s*$", re.IGNORECASE),
    ]

    # Lines to skip inside a transaction section
    _SKIP_PATTERNS = [
        re.compile(r"^\s*Page\s*\d+", re.IGNORECASE),
        re.compile(r"^\s*HDFC\s*Bank", re.IGNORECASE),
        re.compile(r"^\s*-{3,}\s*$"),
        re.compile(r"^\s*={3,}\s*$"),
        re.compile(r"^\s*Date\s+Transaction", re.IGNORECASE),
        re.compile(r"^\s*Date\s+Particulars?", re.IGNORECASE),
        re.compile(r"^\s*Date\s+Description", re.IGNORECASE),
        re.compile(r"^\s*Sr\.?\s*No", re.IGNORECASE),
        re.compile(r"HSN\s*Code", re.IGNORECASE),
        re.compile(r"GSTIN", re.IGNORECASE),
        re.compile(r"Credit\s*Card\s*Statement", re.IGNORECASE),
        re.compile(r"^\s*Infinia\s+Credit\s+Card", re.IGNORECASE),
        re.compile(r"^\s*Regalia\s+", re.IGNORECASE),
        re.compile(r"^\s*Millennia\s+", re.IGNORECASE),
        re.compile(r"^\s*Diners\s+", re.IGNORECASE),
        re.compile(r"^\s*Amount\s*\(.*?\)\s*$", re.IGNORECASE),
        re.compile(r"^\s*Swiggy\s+HDFC", re.IGNORECASE),
        re.compile(r"^\s*DATE\s*&\s*TIME\s+TRANSACTION", re.IGNORECASE),
        re.compile(r"^\s*ANKIT\s+", re.IGNORECASE),  # cardholder name line
        re.compile(r"^\s*[A-Z]+\s+Credit\s+Card\s*$", re.IGNORECASE),
    ]

    def _extract_transactions(
        self, pages: list[str], full_text: str, stmt: ExtractedStatement
    ) -> None:
        """Extract transactions using a line-by-line state machine.

        Strategy:
        1. Scan for section-start markers (e.g. "Domestic Transactions").
        2. Within a section, match transaction lines (date + desc + amount).
        3. Handle continuation lines (description overflow from previous txn).
        4. Stop at section-end markers.
        5. Allow re-entering sections (e.g. International after Domestic).
        """
        lines = full_text.split("\n")

        in_transaction_section = False
        transactions: list[ExtractedTransaction] = []
        pending_txn: ExtractedTransaction | None = None
        # Track how many consecutive non-matching lines we've seen inside a section
        non_match_streak = 0

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if not stripped:
                # Empty line: if we had a pending continuation, finalize it
                if pending_txn is not None:
                    pending_txn = None
                # Don't immediately exit section on single blank line —
                # HDFC statements sometimes have blank lines between txns
                non_match_streak += 1
                if non_match_streak > 3 and in_transaction_section:
                    in_transaction_section = False
                continue

            # ── Always check for section start (even if already in section) ──
            is_section_start = False
            for sp in self._SECTION_STARTS:
                if sp.search(stripped):
                    in_transaction_section = True
                    is_section_start = True
                    non_match_streak = 0
                    pending_txn = None
                    break

            if is_section_start:
                continue

            # ── Check for section end ──
            if in_transaction_section:
                is_section_end = False
                for ep in self._SECTION_ENDS:
                    if ep.search(stripped):
                        is_section_end = True
                        break
                if is_section_end:
                    in_transaction_section = False
                    pending_txn = None
                    non_match_streak = 0
                    continue

            if not in_transaction_section:
                continue

            # ── Skip known non-transaction lines ──
            should_skip = False
            for skip in self._SKIP_PATTERNS:
                if skip.search(stripped):
                    should_skip = True
                    break
            if should_skip:
                continue

            # ── Try to match a full transaction line ──
            m = self._TXN_PATTERN.match(stripped)
            if m:
                date_str = m.group(1)
                description = m.group(2).strip()
                plus_sign = m.group(3)  # '+' credit indicator
                amount_str = m.group(4)
                cr_dr = m.group(5)

                txn_date = parse_indian_date(date_str)
                if not txn_date:
                    non_match_streak += 1
                    continue

                amount = parse_indian_amount(amount_str)
                if amount is None or amount == 0:
                    non_match_streak += 1
                    continue

                # Clean up description
                description = re.sub(r"\s{2,}", " ", description)

                # Credit card: default is debit (purchase).
                # Cr or + means credit (payment/refund).
                is_credit = (
                    (cr_dr and cr_dr.upper() == "CR")
                    or (plus_sign == "+")
                )
                direction = "credit" if is_credit else "debit"

                txn = ExtractedTransaction(
                    transaction_date=txn_date,
                    posting_date=None,
                    description=description,
                    amount=amount,
                    direction=direction,
                    line_number=line_num,
                )
                transactions.append(txn)
                pending_txn = txn
                non_match_streak = 0

            elif pending_txn is not None and not stripped[0:1].isdigit():
                # Continuation line: append to previous transaction's description
                pending_txn.description += " " + stripped
                # Keep pending_txn set for multi-line continuations
                non_match_streak = 0
            else:
                # Unrecognized line inside section
                non_match_streak += 1
                pending_txn = None

                # Heuristic: if too many unrecognized lines, probably left the section
                if non_match_streak > 8:
                    in_transaction_section = False

        # ── Fallback: if no section markers were found, try to match ──
        # transaction lines across the entire text (some statements lack headers)
        if not transactions:
            transactions = self._fallback_extract(lines)

        stmt.transactions = transactions

    def _fallback_extract(self, lines: list[str]) -> list[ExtractedTransaction]:
        """Fallback extraction: try matching transaction lines across all text.

        Used when the section-based approach finds nothing — e.g. when the
        text extraction doesn't preserve section headers.
        """
        transactions: list[ExtractedTransaction] = []
        pending_txn: ExtractedTransaction | None = None

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                pending_txn = None
                continue

            # Skip obvious non-transaction lines
            if any(skip.search(stripped) for skip in self._SKIP_PATTERNS):
                continue
            if any(ep.search(stripped) for ep in self._SECTION_ENDS):
                continue

            m = self._TXN_PATTERN.match(stripped)
            if m:
                date_str = m.group(1)
                description = m.group(2).strip()
                plus_sign = m.group(3)
                amount_str = m.group(4)
                cr_dr = m.group(5)

                txn_date = parse_indian_date(date_str)
                if not txn_date:
                    continue

                amount = parse_indian_amount(amount_str)
                if amount is None or amount == 0:
                    continue

                description = re.sub(r"\s{2,}", " ", description)
                is_credit = (cr_dr and cr_dr.upper() == "CR") or (plus_sign == "+")
                direction = "credit" if is_credit else "debit"

                txn = ExtractedTransaction(
                    transaction_date=txn_date,
                    posting_date=None,
                    description=description,
                    amount=amount,
                    direction=direction,
                    line_number=line_num,
                )
                transactions.append(txn)
                pending_txn = txn

            elif pending_txn is not None and not stripped[0:1].isdigit():
                pending_txn.description += " " + stripped
                pending_txn = None

        return transactions


# Register this parser
register_parser(HdfcCreditCardParser())
