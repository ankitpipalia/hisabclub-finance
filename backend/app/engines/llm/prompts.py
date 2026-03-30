"""Prompt templates and few-shot examples for statement LLM workflows."""

from __future__ import annotations

from dataclasses import dataclass


STATEMENT_CLASSIFICATION_PROMPT_VERSION = "statement_classification_v2"
STATEMENT_EXTRACTION_PROMPT_VERSION = "statement_extraction_v2"


@dataclass(frozen=True)
class FewShotExample:
    bank: str
    account_type: str
    user: str
    assistant: str


_EXAMPLES: tuple[FewShotExample, ...] = (
    FewShotExample(
        bank="HDFC",
        account_type="credit_card",
        user=(
            "Chunk text:\n"
            "Date Description Amount\n"
            "12/02/2026 PAYMENT RECEIVED-NEFT 15000.00 CR\n"
            "14/02/2026 AMAZON SELLER SERVICES 1249.00 DR"
        ),
        assistant=(
            '{"bank_name":"HDFC","account_type":"credit_card","account_number_masked":"XX1234",'
            '"statement_period_start":null,"statement_period_end":null,"opening_balance":null,'
            '"closing_balance":null,"transactions":[{"date":"2026-02-12","description":"PAYMENT RECEIVED-NEFT",'
            '"amount":15000.00,"direction":"credit","reference_number":null,"confidence":0.95},'
            '{"date":"2026-02-14","description":"AMAZON SELLER SERVICES","amount":1249.00,'
            '"direction":"debit","reference_number":null,"confidence":0.93}]}'  # noqa: E501
        ),
    ),
    FewShotExample(
        bank="AXIS",
        account_type="savings",
        user=(
            "Chunk text:\n"
            "18-01-2026 UPI/DR/600123/PHONEPE 850.00 10322.12\n"
            "18-01-2026 UPI/CR/600124/REFUND 850.00 11172.12"
        ),
        assistant=(
            '{"bank_name":"AXIS","account_type":"savings","account_number_masked":"XX7788",'
            '"statement_period_start":null,"statement_period_end":null,"opening_balance":null,'
            '"closing_balance":null,"transactions":[{"date":"2026-01-18","description":"UPI/DR/600123/PHONEPE",'
            '"amount":850.00,"direction":"debit","reference_number":"600123","confidence":0.91},'
            '{"date":"2026-01-18","description":"UPI/CR/600124/REFUND","amount":850.00,'
            '"direction":"credit","reference_number":"600124","confidence":0.91}]}'  # noqa: E501
        ),
    ),
    FewShotExample(
        bank="SBI",
        account_type="savings",
        user=(
            "Chunk text:\n"
            "20/03/2026 NEFT CR-SALARY ACME PVT LTD 78500.00\n"
            "22/03/2026 ATM WDL 5000.00"
        ),
        assistant=(
            '{"bank_name":"SBI","account_type":"savings","account_number_masked":"XX9999",'
            '"statement_period_start":null,"statement_period_end":null,"opening_balance":null,'
            '"closing_balance":null,"transactions":[{"date":"2026-03-20","description":"NEFT CR-SALARY ACME PVT LTD",'
            '"amount":78500.00,"direction":"credit","reference_number":null,"confidence":0.92},'
            '{"date":"2026-03-22","description":"ATM WDL","amount":5000.00,'
            '"direction":"debit","reference_number":null,"confidence":0.90}]}'  # noqa: E501
        ),
    ),
)


def build_statement_classification_system_prompt() -> str:
    return (
        "You classify Indian financial statement documents.\n"
        "Return strict JSON only:\n"
        '{"bank_name":"string|null","account_type":"credit_card|savings|current|unknown",'
        '"confidence":0..1,"reason":"<=25 words"}\n'
        "Rules:\n"
        "- Use only the current document text as primary truth.\n"
        "- Customer history can support but never override explicit current text.\n"
        "- Prefer unknown over guessing."
    )


def build_statement_extraction_system_prompt() -> str:
    return (
        "You are a financial statement transaction extractor for Indian bank/card statements.\n"
        "Return strict JSON only. Never include markdown.\n"
        "Output schema:\n"
        "{"
        '"bank_name":"string|null",'
        '"account_type":"credit_card|savings|current|unknown",'
        '"account_number_masked":"string|null",'
        '"statement_period_start":"YYYY-MM-DD|null",'
        '"statement_period_end":"YYYY-MM-DD|null",'
        '"opening_balance":"number|null",'
        '"closing_balance":"number|null",'
        '"transactions":[{'
        '"date":"YYYY-MM-DD",'
        '"description":"string",'
        '"amount":"number-positive",'
        '"direction":"debit|credit",'
        '"reference_number":"string|null",'
        '"confidence":"0..1"'
        "}]"
        "}\n"
        "Rules:\n"
        "- Extract only what is present in the chunk.\n"
        "- Amount must be absolute positive number.\n"
        "- Use direction for debit/credit sign semantics.\n"
        "- For date-less rows, carry forward previous row date inside that chunk.\n"
        "- If unsure, keep confidence below 0.6."
    )


def few_shot_messages(
    *,
    bank_hint: str | None,
    account_type_hint: str | None,
    max_examples: int = 2,
) -> list[dict[str, str]]:
    normalized_bank = (bank_hint or "").strip().upper()
    normalized_type = (account_type_hint or "").strip().lower()
    candidates: list[FewShotExample] = []

    for item in _EXAMPLES:
        if normalized_bank and item.bank != normalized_bank:
            continue
        if normalized_type and normalized_type not in {"auto", "bank_account"}:
            if item.account_type != normalized_type:
                continue
        if normalized_type == "bank_account" and item.account_type == "credit_card":
            continue
        candidates.append(item)

    if not candidates:
        candidates = list(_EXAMPLES[:max_examples])
    else:
        candidates = candidates[:max_examples]

    messages: list[dict[str, str]] = []
    for example in candidates:
        messages.append({"role": "user", "content": example.user})
        messages.append({"role": "assistant", "content": example.assistant})
    return messages

