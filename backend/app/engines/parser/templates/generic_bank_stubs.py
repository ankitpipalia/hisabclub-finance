"""Metadata-only parser stubs for banks observed in FY24-25 ingestion.

These stubs intentionally do not extract transactions yet. They give the
orchestrator a deterministic bank/account-type match and then let the existing
LLM fallback handle transaction extraction until full template parsers are built.
"""

from __future__ import annotations

import re

from app.engines.parser.amount_utils import parse_indian_amount, parse_indian_date
from app.engines.parser.base import ExtractedStatement, StatementParser, register_parser


class _MetadataOnlyParser(StatementParser):
    _bank_pattern: str = ""
    _statement_pattern: str = (
        r"Account\s*Statement|Statement\s*of\s*Account|Transaction\s*Statement|"
        r"Savings\s*Account|Current\s*Account"
    )
    _credit_card_pattern: str = (
        r"Credit\s*Card\s*Statement|Card\s*Statement|Minimum\s*Amount\s*Due|"
        r"Total\s*Amount\s*Due|Payment\s*Due\s*Date"
    )

    def detect(self, text: str) -> bool:
        has_bank = bool(re.search(self._bank_pattern, text, re.IGNORECASE))
        if self.account_type == "credit_card":
            return has_bank and bool(re.search(self._credit_card_pattern, text, re.IGNORECASE))
        return (
            has_bank
            and bool(re.search(self._statement_pattern, text, re.IGNORECASE))
            and not bool(re.search(self._credit_card_pattern, text, re.IGNORECASE))
        )

    def parse(self, pages: list[str], full_text: str) -> ExtractedStatement:
        stmt = ExtractedStatement(
            bank_name=self.bank_name,
            account_type=self.account_type,
            parser_id=self.parser_id,
            warnings=[
                "Metadata-only parser stub matched this statement; "
                "transaction extraction should use local LLM fallback."
            ],
        )
        self._extract_common_metadata(full_text, stmt)
        return stmt

    def _extract_common_metadata(self, text: str, stmt: ExtractedStatement) -> None:
        m = re.search(
            r"(?:Account|A/c|Card)\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([Xx*\d][Xx*\d\s\-]{5,22})",
            text,
            re.IGNORECASE,
        )
        if m:
            digits = re.sub(r"\D", "", m.group(1))
            masked = re.sub(r"[\s\-]", "", m.group(1)).upper()
            if len(digits) >= 4:
                stmt.account_number_masked = "X" * max(0, len(digits) - 4) + digits[-4:]
            elif masked:
                stmt.account_number_masked = masked[-12:]

        for pat in (
            r"(?:Statement|Period|From)\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|To|-)\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
            r"(?:Statement|Period|From)\s*[:\-]?\s*(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4})\s*(?:to|To|-)\s*(\d{1,2}[\s/\-]\w{3,9}[\s/\-]\d{2,4})",
            r"(\d{1,2}[/\-]\w{3}[/\-]\d{4})\s*(?:to|-)\s*(\d{1,2}[/\-]\w{3}[/\-]\d{4})",
        ):
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                stmt.statement_period_start = parse_indian_date(m.group(1))
                stmt.statement_period_end = parse_indian_date(m.group(2))
                break

        m = re.search(
            r"Opening\s*Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.opening_balance = parse_indian_amount(m.group(1))

        m = re.search(
            r"Closing\s*Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        if m:
            stmt.closing_balance = parse_indian_amount(m.group(1))


class IciciSavingsParserStub(_MetadataOnlyParser):
    _bank_pattern = r"ICICI\s*Bank|\bICICI\b"

    @property
    def parser_id(self) -> str:
        return "icici_savings_stub_v1"

    @property
    def bank_name(self) -> str:
        return "ICICI"

    @property
    def account_type(self) -> str:
        return "savings"


class KotakSavingsParserStub(_MetadataOnlyParser):
    _bank_pattern = r"Kotak\s*Mahindra|Kotak\s*Bank|\bKotak\b"

    @property
    def parser_id(self) -> str:
        return "kotak_savings_stub_v1"

    @property
    def bank_name(self) -> str:
        return "KOTAK"

    @property
    def account_type(self) -> str:
        return "savings"


class KotakCreditCardParserStub(_MetadataOnlyParser):
    _bank_pattern = r"Kotak\s*Mahindra|Kotak\s*Bank|\bKotak\b"

    @property
    def parser_id(self) -> str:
        return "kotak_cc_stub_v1"

    @property
    def bank_name(self) -> str:
        return "KOTAK"

    @property
    def account_type(self) -> str:
        return "credit_card"


register_parser(IciciSavingsParserStub())
register_parser(KotakSavingsParserStub())
register_parser(KotakCreditCardParserStub())
