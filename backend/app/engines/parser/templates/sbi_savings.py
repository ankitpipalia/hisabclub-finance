"""SBI (State Bank of India) Savings/Current Account Statement Parser.

Handles SBI bank account statement PDFs.
Statement format typically has columns:
  Txn Date | Value Date | Description | Ref No./Cheque No. | Debit | Credit | Balance

Also handles:
  Date | Particulars | Withdrawal | Deposit | Balance
  Date | Description | Amount | Cr/Dr
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


class SbiSavingsParser(StatementParser):
    @property
    def parser_id(self) -> str:
        return "sbi_savings_v1"

    @property
    def bank_name(self) -> str:
        return "SBI"

    @property
    def account_type(self) -> str:
        return "savings"

    def detect(self, text: str) -> bool:
        has_sbi = bool(re.search(r"State\s*Bank\s*of\s*India|SBI\b", text, re.IGNORECASE))
        has_savings = bool(
            re.search(
                r"Savings\s*Account|Current\s*Account|Account\s*Statement|"
                r"Statement\s*of\s*Account|Passbook|Transaction\s*Statement",
                text,
                re.IGNORECASE,
            )
        )
        # Must NOT be a credit card (SBI Card)
        is_cc = bool(
            re.search(
                r"SBI\s*Card|Credit\s*Card\s*Statement",
                text,
                re.IGNORECASE,
            )
        )
        return has_sbi and has_savings and not is_cc

    def parse(self, pages: list[str], full_text: str) -> ExtractedStatement:
        stmt = ExtractedStatement(
            bank_name=self.bank_name,
            account_type=self.account_type,
            parser_id=self.parser_id,
        )
        self._extract_metadata(full_text, stmt)
        self._extract_transactions(full_text, stmt)
        return stmt

    # ── Metadata ────────────────────────────────────────────

    def _extract_metadata(self, text: str, stmt: ExtractedStatement) -> None:
        # Account number — SBI uses various formats
        m = re.search(
            r"(?:Account|A/c)\s*(?:No\.?|Number|#)\s*[:\-]?\s*(\d[\d\s]{8,18}\d)",
            text,
            re.IGNORECASE,
        )
        if m:
            raw = m.group(1).replace(" ", "")
            if len(raw) > 4:
                stmt.account_number_masked = "X" * (len(raw) - 4) + raw[-4:]
            else:
                stmt.account_number_masked = raw

        # Statement period
        for pat in [
            r"(?:Statement|Period|From)\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|To|-)\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
            r"(?:Statement|Period)\s*[:\-]?\s*(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4})\s*(?:to|To|-)\s*(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4})",
            r"(\d{1,2}[/\-]\w{3}[/\-]\d{4})\s*(?:to|-)\s*(\d{1,2}[/\-]\w{3}[/\-]\d{4})",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                stmt.statement_period_start = parse_indian_date(m.group(1))
                stmt.statement_period_end = parse_indian_date(m.group(2))
                break

        # Opening balance
        m = re.search(
            r"Opening\s*Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.opening_balance = parse_indian_amount(m.group(1))

        # Closing balance
        m = re.search(
            r"Closing\s*Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.closing_balance = parse_indian_amount(m.group(1))

    # ── Transaction extraction ──────────────────────────────

    # SBI commonly has Txn Date and Value Date on the same line:
    # DD/MM/YYYY DD/MM/YYYY DESCRIPTION REF_NO DEBIT CREDIT BALANCE
    # Or simpler: DD/MM/YYYY DESCRIPTION AMOUNT BALANCE

    # Pattern with two dates + 3 amounts: txn_date value_date desc debit credit balance
    _TXN_2DATE_3AMT = re.compile(
        r"^\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"  # txn date
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"        # value date
        r"(.+?)\s+"                                       # description
        r"([\d,]+\.\d{2})\s+"                             # debit
        r"([\d,]+\.\d{2})\s+"                             # credit
        r"([\d,]+\.\d{2})\s*$"                            # balance
    )

    # Pattern with one date + 3 amounts: date desc debit credit balance
    _TXN_3AMT = re.compile(
        r"^\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"  # date
        r"(.+?)\s+"                                      # description
        r"([\d,]+\.\d{2})\s+"                            # amount1 (debit)
        r"([\d,]+\.\d{2})\s+"                            # amount2 (credit)
        r"([\d,]+\.\d{2})\s*$"                           # amount3 (balance)
    )

    # Pattern with 2 trailing amounts: amount, balance
    _TXN_2AMT = re.compile(
        r"^\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"  # date
        r"(.+?)\s+"                                      # description
        r"([\d,]+\.\d{2})\s+"                            # amount
        r"([\d,]+\.\d{2})\s*$"                           # balance
    )

    # Pattern with Cr/Dr label
    _TXN_LABELLED = re.compile(
        r"^\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"
        r"(.+?)\s+"
        r"([\d,]+\.\d{2})\s*"
        r"(Cr|Dr|CR|DR|C|D)\s*$"
    )

    _SECTION_STARTS = [
        re.compile(r"(?:Txn|Tran(?:saction)?)\s*Date", re.IGNORECASE),
        re.compile(r"Date\s+(?:Narration|Description|Particulars?)", re.IGNORECASE),
        re.compile(r"Transaction\s+Details?", re.IGNORECASE),
    ]

    _SECTION_ENDS = [
        re.compile(r"Closing\s*Balance", re.IGNORECASE),
        re.compile(r"Statement\s*Summary", re.IGNORECASE),
        re.compile(r"Terms\s*(?:and|&)\s*Condition", re.IGNORECASE),
        re.compile(r"This\s+is\s+a\s+(?:computer|system)\s+generated", re.IGNORECASE),
        re.compile(r"^\s*\*{3,}"),
    ]

    _SKIP_PATTERNS = [
        re.compile(r"^\s*(?:Txn|Tran)\s*Date", re.IGNORECASE),
        re.compile(r"^\s*Date\s+(?:Narration|Description|Particulars|Value)", re.IGNORECASE),
        re.compile(r"^\s*Page\s*\d+", re.IGNORECASE),
        re.compile(r"^\s*-{3,}\s*$"),
        re.compile(r"^\s*={3,}\s*$"),
        re.compile(r"State\s*Bank", re.IGNORECASE),
        re.compile(r"^\s*Withdrawal\s+Deposit\s+Balance", re.IGNORECASE),
        re.compile(r"^\s*Debit\s+Credit\s+Balance", re.IGNORECASE),
        re.compile(r"^\s*Opening\s*Balance", re.IGNORECASE),
    ]

    def _extract_transactions(self, text: str, stmt: ExtractedStatement) -> None:
        lines = text.split("\n")
        in_section = False
        transactions: list[ExtractedTransaction] = []
        pending_txn: ExtractedTransaction | None = None
        non_match_streak = 0
        prev_balance: float | None = stmt.opening_balance

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if not stripped:
                pending_txn = None
                non_match_streak += 1
                if non_match_streak > 3 and in_section:
                    in_section = False
                continue

            # Check section start
            if any(sp.search(stripped) for sp in self._SECTION_STARTS):
                in_section = True
                non_match_streak = 0
                continue

            # Check section end
            if in_section and any(ep.search(stripped) for ep in self._SECTION_ENDS):
                in_section = False
                pending_txn = None
                continue

            if not in_section:
                continue

            # Skip headers
            if any(sp.search(stripped) for sp in self._SKIP_PATTERNS):
                continue

            # Try 2-date + 3-amount pattern (SBI-specific with value date)
            m = self._TXN_2DATE_3AMT.match(stripped)
            if m:
                txn = self._parse_2date_3amt(m, line_num, prev_balance)
                if txn:
                    transactions.append(txn)
                    pending_txn = txn
                    non_match_streak = 0
                    balance = parse_indian_amount(m.group(6))
                    if balance is not None:
                        prev_balance = balance
                continue

            # Try 3-amount pattern
            m = self._TXN_3AMT.match(stripped)
            if m:
                txn = self._parse_3amt(m, line_num, prev_balance)
                if txn:
                    transactions.append(txn)
                    pending_txn = txn
                    non_match_streak = 0
                    balance = parse_indian_amount(m.group(5))
                    if balance is not None:
                        prev_balance = balance
                continue

            # Try 2-amount pattern
            m = self._TXN_2AMT.match(stripped)
            if m:
                txn = self._parse_2amt(m, line_num, prev_balance)
                if txn:
                    transactions.append(txn)
                    pending_txn = txn
                    non_match_streak = 0
                    balance = parse_indian_amount(m.group(4))
                    if balance is not None:
                        prev_balance = balance
                continue

            # Try labelled pattern
            m = self._TXN_LABELLED.match(stripped)
            if m:
                txn = self._parse_labelled(m, line_num)
                if txn:
                    transactions.append(txn)
                    pending_txn = txn
                    non_match_streak = 0
                continue

            # Continuation line
            if pending_txn is not None and not stripped[0:1].isdigit():
                pending_txn.description += " " + stripped
                non_match_streak = 0
            else:
                non_match_streak += 1
                pending_txn = None
                if non_match_streak > 8:
                    in_section = False

        # Fallback
        if not transactions:
            transactions = self._fallback_extract(lines, prev_balance)

        stmt.transactions = transactions

    def _parse_2date_3amt(
        self, m: re.Match, line_num: int, prev_balance: float | None
    ) -> ExtractedTransaction | None:
        """Parse SBI line with txn date, value date, desc, debit, credit, balance."""
        txn_date = parse_indian_date(m.group(1))
        value_date = parse_indian_date(m.group(2))
        if not txn_date:
            return None
        desc = re.sub(r"\s{2,}", " ", m.group(3).strip())
        amt_debit = parse_indian_amount(m.group(4))
        amt_credit = parse_indian_amount(m.group(5))
        balance = parse_indian_amount(m.group(6))

        has_debit = amt_debit is not None and amt_debit > 0
        has_credit = amt_credit is not None and amt_credit > 0

        if has_debit and not has_credit:
            return ExtractedTransaction(
                transaction_date=txn_date, posting_date=value_date,
                description=desc, amount=amt_debit, direction="debit",
                line_number=line_num,
            )
        if has_credit and not has_debit:
            return ExtractedTransaction(
                transaction_date=txn_date, posting_date=value_date,
                description=desc, amount=amt_credit, direction="credit",
                line_number=line_num,
            )
        if has_debit and has_credit and prev_balance is not None and balance is not None:
            direction = "credit" if balance > prev_balance else "debit"
            amount = amt_credit if direction == "credit" else amt_debit
            return ExtractedTransaction(
                transaction_date=txn_date, posting_date=value_date,
                description=desc, amount=amount, direction=direction,
                line_number=line_num,
            )
        return None

    def _parse_3amt(
        self, m: re.Match, line_num: int, prev_balance: float | None
    ) -> ExtractedTransaction | None:
        txn_date = parse_indian_date(m.group(1))
        if not txn_date:
            return None
        desc = re.sub(r"\s{2,}", " ", m.group(2).strip())
        amt1 = parse_indian_amount(m.group(3))
        amt2 = parse_indian_amount(m.group(4))
        balance = parse_indian_amount(m.group(5))

        has_amt1 = amt1 is not None and amt1 > 0
        has_amt2 = amt2 is not None and amt2 > 0

        if has_amt1 and not has_amt2:
            return ExtractedTransaction(
                transaction_date=txn_date, posting_date=None,
                description=desc, amount=amt1, direction="debit", line_number=line_num,
            )
        if has_amt2 and not has_amt1:
            return ExtractedTransaction(
                transaction_date=txn_date, posting_date=None,
                description=desc, amount=amt2, direction="credit", line_number=line_num,
            )
        if has_amt1 and has_amt2 and prev_balance is not None and balance is not None:
            direction = "credit" if balance > prev_balance else "debit"
            amount = amt2 if direction == "credit" else amt1
            return ExtractedTransaction(
                transaction_date=txn_date, posting_date=None,
                description=desc, amount=amount, direction=direction, line_number=line_num,
            )
        return None

    def _parse_2amt(
        self, m: re.Match, line_num: int, prev_balance: float | None
    ) -> ExtractedTransaction | None:
        txn_date = parse_indian_date(m.group(1))
        if not txn_date:
            return None
        desc = re.sub(r"\s{2,}", " ", m.group(2).strip())
        amount = parse_indian_amount(m.group(3))
        balance = parse_indian_amount(m.group(4))
        if not amount or amount == 0:
            return None
        direction = _infer_direction(desc, amount, balance, prev_balance)
        return ExtractedTransaction(
            transaction_date=txn_date, posting_date=None,
            description=desc, amount=amount, direction=direction, line_number=line_num,
        )

    def _parse_labelled(
        self, m: re.Match, line_num: int
    ) -> ExtractedTransaction | None:
        txn_date = parse_indian_date(m.group(1))
        if not txn_date:
            return None
        desc = re.sub(r"\s{2,}", " ", m.group(2).strip())
        amount = parse_indian_amount(m.group(3))
        cr_dr = m.group(4)
        if not amount or amount == 0:
            return None
        direction = "credit" if cr_dr and cr_dr.upper() in ("CR", "C") else "debit"
        return ExtractedTransaction(
            transaction_date=txn_date, posting_date=None,
            description=desc, amount=amount, direction=direction, line_number=line_num,
        )

    def _fallback_extract(
        self, lines: list[str], prev_balance: float | None
    ) -> list[ExtractedTransaction]:
        """Try matching transaction lines across all text without section markers."""
        transactions: list[ExtractedTransaction] = []

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or len(stripped) < 15:
                continue
            if any(sp.search(stripped) for sp in self._SKIP_PATTERNS):
                continue

            # Try patterns in order of specificity
            m = self._TXN_2DATE_3AMT.match(stripped)
            if m:
                txn = self._parse_2date_3amt(m, line_num, prev_balance)
                if txn:
                    transactions.append(txn)
                    balance = parse_indian_amount(m.group(6))
                    if balance is not None:
                        prev_balance = balance
                continue

            m = self._TXN_3AMT.match(stripped)
            if m:
                txn = self._parse_3amt(m, line_num, prev_balance)
                if txn:
                    transactions.append(txn)
                    balance = parse_indian_amount(m.group(5))
                    if balance is not None:
                        prev_balance = balance
                continue

            m = self._TXN_2AMT.match(stripped)
            if m:
                txn = self._parse_2amt(m, line_num, prev_balance)
                if txn:
                    transactions.append(txn)
                    balance = parse_indian_amount(m.group(4))
                    if balance is not None:
                        prev_balance = balance
                continue

            m = self._TXN_LABELLED.match(stripped)
            if m:
                txn = self._parse_labelled(m, line_num)
                if txn:
                    transactions.append(txn)

        return transactions


def _infer_direction(
    desc: str,
    amount: float,
    balance: float | None,
    prev_balance: float | None,
) -> str:
    """Infer debit/credit direction from balance movement or description keywords."""
    if prev_balance is not None and balance is not None:
        return "credit" if balance > prev_balance else "debit"
    desc_upper = desc.upper()
    credit_keywords = [
        "SALARY", "NEFT CR", "RTGS CR", "IMPS CR", "CREDIT", "REFUND",
        "CASHBACK", "INTEREST", "BY TRANSFER", "RECEIVED", "INT.CREDIT",
    ]
    if any(kw in desc_upper for kw in credit_keywords):
        return "credit"
    return "debit"


register_parser(SbiSavingsParser())
