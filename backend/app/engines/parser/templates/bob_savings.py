"""Bank of Baroda savings account statement parser.

Real FY24-25 BOB PDFs expose this logical layout:
TRAN DATE | VALUE DATE | NARRATION | CHQ.NO. | WITHDRAWAL(DR) | DEPOSIT(CR) | BALANCE(INR)

The text layer collapses empty withdrawal/deposit columns, so direction is inferred
from chronological balance deltas rather than by guessing with an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.engines.parser.base import (
    ExtractedStatement,
    ExtractedTransaction,
    StatementParser,
    register_parser,
)

HEADER_ACCOUNT_RE = re.compile(
    r"Account\s*(?:Number|No\.?)\s*[:\-]?\s*([\dXx*\s\-]{8,})", re.IGNORECASE
)
HEADER_PERIOD_RE = re.compile(
    r"(?:Statement\s+Period\s+from|Statement\s+Period|Period|for\s+the\s+period)\s*[:\-]?\s*"
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|To|-)\s*"
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
    re.IGNORECASE,
)
HEADER_OPENING_RE = re.compile(
    r"Opening\s+Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
    re.IGNORECASE,
)
HEADER_CLOSING_RE = re.compile(
    r"Closing\s+Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
    re.IGNORECASE,
)
TABLE_HEADER_RE = re.compile(
    r"TRAN\s+DATE\s+VALUE\s+DATE\s+NARRATION.*WITHDRAWAL\(DR\).*DEPOSIT\(CR\).*BALANCE\(INR\)",
    re.IGNORECASE,
)
DATE_START_RE = re.compile(r"^(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(.+)$")
DATE_ONLY_RE = re.compile(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$")
SKIP_LINE_RE = re.compile(
    r"^[-=\s]+$|^Main Account Holder|^Address\s*:|^Customer Id|^Branch Name|"
    r"^IFSC Code|^Your Account Statement|^Statement of transactions|^Page\s+\d+|"
    r"computer-generated statement|Contact-Us@",
    re.IGNORECASE,
)
AMOUNT_TOKEN_RE = re.compile(
    r"^(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?(?:Cr|Dr)?$",
    re.IGNORECASE,
)
BALANCE_TOKEN_RE = re.compile(
    r"^(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?(?:Cr|Dr)$", re.IGNORECASE
)
REF_RE = re.compile(r"\b([A-Z0-9][A-Z0-9/\-:]{5,})\b", re.IGNORECASE)
BALANCE_TOLERANCE = Decimal("0.02")


@dataclass
class BOBStatementMeta:
    account_number: str
    period_start: date | None
    period_end: date | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None


@dataclass
class BOBRawRow:
    txn_date: date
    narration: str
    ref_number: str
    value_date: date | None
    withdrawal: Decimal | None
    deposit: Decimal | None
    balance: Decimal | None
    page_number: int
    line_number: int
    amount: Decimal | None = None


@dataclass
class _ParsedLine:
    txn_date: date
    narration: str
    value_date: date | None
    amount: Decimal
    balance: Decimal | None
    ref_number: str
    page_number: int
    line_number: int


def parse_amount(value: str) -> Decimal | None:
    if not value:
        return None
    cleaned = str(value).strip()
    if not cleaned or cleaned.upper() in {"N/A", "NA", "-"}:
        return None
    cleaned = re.sub(r"(?:Rs\.?|INR|₹)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[Cc]r$|[Dd]r$", "", cleaned).replace(",", "").strip()
    try:
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None


def parse_date_str(value: str) -> date | None:
    text = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d-%b-%Y", "%d/%b/%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_balance(value: str) -> Decimal | None:
    amount = parse_amount(value)
    if amount is None:
        return None
    if str(value).strip().lower().endswith("dr"):
        return -amount
    return amount


def extract_meta(full_text: str) -> BOBStatementMeta:
    account = ""
    match = HEADER_ACCOUNT_RE.search(full_text)
    if match:
        account = re.sub(r"\s+", "", match.group(1)).upper()

    period_start = period_end = None
    match = HEADER_PERIOD_RE.search(full_text)
    if match:
        period_start = parse_date_str(match.group(1))
        period_end = parse_date_str(match.group(2))

    opening = closing = None
    match = HEADER_OPENING_RE.search(full_text)
    if match:
        opening = parse_amount(match.group(1))
    match = HEADER_CLOSING_RE.search(full_text)
    if match:
        closing = parse_amount(match.group(1))

    rows = extract_transactions([full_text])
    if rows:
        if opening is None:
            opening = _infer_opening_balance(rows)
        if closing is None:
            closing = rows[-1].balance

    return BOBStatementMeta(account, period_start, period_end, opening, closing)


def extract_transactions(pages_text: list[str]) -> list[BOBRawRow]:
    parsed_rows: list[_ParsedLine] = []
    in_table = False
    current: _ParsedLine | None = None

    for page_num, text in enumerate(pages_text, start=1):
        for line_num, raw_line in enumerate(text.splitlines()):
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            if TABLE_HEADER_RE.search(line):
                in_table = True
                continue
            if not in_table or SKIP_LINE_RE.search(line):
                continue

            parsed = _parse_transaction_line(line, page_num=page_num, line_number=line_num)
            if parsed is not None:
                parsed_rows.append(parsed)
                current = parsed
                continue

            if current is not None and not _looks_like_footer(line):
                current.narration = f"{current.narration} {line}".strip()
                current.ref_number = current.ref_number or _extract_reference(current.narration)

    return _infer_direction_rows(parsed_rows)


def to_raw_transaction(row: BOBRawRow):
    from app.extraction.models import ExtractionSource, RawTransaction

    if row.withdrawal is not None and row.deposit is None:
        txn_type_raw = "DR"
        amount_raw = str(row.withdrawal)
        confidence = 0.98
    elif row.deposit is not None and row.withdrawal is None:
        txn_type_raw = "CR"
        amount_raw = str(row.deposit)
        confidence = 0.98
    else:
        txn_type_raw = "?"
        amount_raw = str(row.amount or row.withdrawal or row.deposit or "0")
        confidence = 0.4

    return RawTransaction(
        date_raw=row.txn_date.strftime("%d/%m/%Y"),
        description_raw=row.narration,
        amount_raw=amount_raw,
        balance_raw=str(row.balance) if row.balance is not None else None,
        txn_type_raw=txn_type_raw,
        page_number=row.page_number,
        char_offset=row.line_number,
        confidence=confidence,
        source=ExtractionSource.TEMPLATE,
        source_evidence={
            "narration": row.narration,
            "ref_number": row.ref_number,
            "withdrawal": str(row.withdrawal) if row.withdrawal is not None else None,
            "deposit": str(row.deposit) if row.deposit is not None else None,
            "balance": str(row.balance) if row.balance is not None else None,
            "value_date": row.value_date.isoformat() if row.value_date else None,
            "parser_id": "bob_savings_v1",
        },
    )


class BobSavingsParser(StatementParser):
    @property
    def parser_id(self) -> str:
        return "bob_savings_v1"

    @property
    def bank_name(self) -> str:
        return "BOB"

    @property
    def account_type(self) -> str:
        return "savings"

    def detect(self, text: str) -> bool:
        has_bob = bool(re.search(r"Bank\s*of\s*Baroda|\bBOB\b|BARB0", text, re.IGNORECASE))
        has_layout = bool(TABLE_HEADER_RE.search(text)) or bool(
            re.search(
                r"Statement\s+of\s+transactions\s+in\s+Savings\s+Account",
                text,
                re.IGNORECASE,
            )
        )
        is_cc = bool(
            re.search(
                r"Credit\s*Card\s*Statement|Minimum\s*Amount\s*Due",
                text,
                re.IGNORECASE,
            )
        )
        return has_bob and has_layout and not is_cc

    def parse(self, pages: list[str], full_text: str) -> ExtractedStatement:
        meta = extract_meta(full_text)
        rows = extract_transactions(pages)
        statement = ExtractedStatement(
            bank_name=self.bank_name,
            account_type=self.account_type,
            account_number_masked=_mask_account(meta.account_number),
            statement_period_start=meta.period_start,
            statement_period_end=meta.period_end,
            opening_balance=(
                float(meta.opening_balance) if meta.opening_balance is not None else None
            ),
            closing_balance=(
                float(meta.closing_balance) if meta.closing_balance is not None else None
            ),
            parser_id=self.parser_id,
        )
        statement.transactions = [
            ExtractedTransaction(
                transaction_date=row.txn_date,
                posting_date=row.value_date,
                description=row.narration,
                amount=float(row.withdrawal if row.withdrawal is not None else row.deposit),
                direction="debit" if row.withdrawal is not None else "credit",
                reference_number=row.ref_number or None,
                confidence=0.98,
                line_number=row.line_number,
            )
            for row in rows
            if row.withdrawal is not None or row.deposit is not None
        ]
        if not statement.transactions:
            statement.warnings.append("BOB template matched but found no transactions.")
        if meta.opening_balance is None or meta.closing_balance is None:
            statement.warnings.append("BOB template could not infer opening/closing balance.")
        return statement


def _parse_transaction_line(line: str, *, page_num: int, line_number: int) -> _ParsedLine | None:
    match = DATE_START_RE.match(line)
    if not match:
        return None
    txn_date = parse_date_str(match.group(1))
    if txn_date is None:
        return None

    tokens = match.group(2).split()
    if len(tokens) < 3:
        return None

    value_date = None
    if tokens and DATE_ONLY_RE.fullmatch(tokens[0]):
        value_date = parse_date_str(tokens.pop(0))

    balance_token = _pop_last_matching(tokens, BALANCE_TOKEN_RE)
    amount_token = _pop_last_matching(tokens, AMOUNT_TOKEN_RE)
    if amount_token is None or balance_token is None:
        return None

    amount = parse_amount(amount_token)
    balance = parse_balance(balance_token)
    if amount is None:
        return None

    narration = " ".join(tokens).strip()
    return _ParsedLine(
        txn_date=txn_date,
        narration=narration,
        value_date=value_date,
        amount=amount,
        balance=balance,
        ref_number=_extract_reference(narration),
        page_number=page_num,
        line_number=line_number,
    )


def _pop_last_matching(tokens: list[str], pattern: re.Pattern[str]) -> str | None:
    for index in range(len(tokens) - 1, -1, -1):
        if pattern.fullmatch(tokens[index]):
            return tokens.pop(index)
    return None


def _infer_direction_rows(rows: list[_ParsedLine]) -> list[BOBRawRow]:
    chronological = list(reversed(rows)) if _is_descending_statement(rows) else list(rows)
    output: list[BOBRawRow] = []
    previous_balance: Decimal | None = None

    for index, row in enumerate(chronological):
        is_credit = _infer_direction(row, previous_balance=previous_balance, is_first=index == 0)
        withdrawal = None if is_credit else row.amount
        deposit = row.amount if is_credit else None
        output.append(
            BOBRawRow(
                txn_date=row.txn_date,
                narration=row.narration,
                ref_number=row.ref_number,
                value_date=row.value_date,
                withdrawal=withdrawal,
                deposit=deposit,
                balance=row.balance,
                page_number=row.page_number,
                line_number=row.line_number,
                amount=row.amount,
            )
        )
        previous_balance = row.balance
    return output


def _is_descending_statement(rows: list[_ParsedLine]) -> bool:
    if len(rows) < 2:
        return False
    return rows[0].txn_date > rows[-1].txn_date


def _infer_direction(
    row: _ParsedLine,
    *,
    previous_balance: Decimal | None,
    is_first: bool,
) -> bool:
    if previous_balance is not None and row.balance is not None:
        diff = row.balance - previous_balance
        if abs(abs(diff) - row.amount) <= BALANCE_TOLERANCE:
            return diff > 0

    narration = row.narration.upper()
    credit_tokens = ("INT.PD", "INTEREST", "CLOSURE PROCEEDS", "SALARY", "GIFT", "REFUND")
    debit_tokens = ("CHARGE", "FEE", "DCARDFEE", "PPF-E-PAY", "DR.", "WDL", "WITHDRAW")
    if any(token in narration for token in credit_tokens):
        return True
    if any(token in narration for token in debit_tokens):
        return False
    if is_first and row.amount <= Decimal("10.00"):
        return False
    return False


def _infer_opening_balance(rows: list[BOBRawRow]) -> Decimal | None:
    first = rows[0] if rows else None
    if first is None or first.balance is None or first.amount is None:
        return None
    if first.deposit is not None:
        return first.balance - first.deposit
    if first.withdrawal is not None:
        return first.balance + first.withdrawal
    return None


def _extract_reference(narration: str) -> str:
    match = REF_RE.search(narration or "")
    return match.group(1) if match else ""


def _mask_account(account: str) -> str | None:
    if not account:
        return None
    normalized = re.sub(r"\s+", "", account).upper()
    digits = re.sub(r"\D", "", normalized)
    if "X" in normalized or "*" in normalized:
        return normalized
    if len(digits) >= 4:
        return "X" * max(0, len(digits) - 4) + digits[-4:]
    return normalized or None


def _looks_like_footer(line: str) -> bool:
    return bool(SKIP_LINE_RE.search(line) or line.lower().startswith("total"))


register_parser(BobSavingsParser())
