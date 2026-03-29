from __future__ import annotations

from dataclasses import dataclass
import re


BANK_ALIASES: dict[str, str] = {
    "SBI": "SBI",
    "STATE BANK OF INDIA": "SBI",
    "STATE_BANK_OF_INDIA": "SBI",
    "HDFC": "HDFC",
    "HDFC BANK": "HDFC",
    "ICICI": "ICICI",
    "ICICI BANK": "ICICI",
    "AXIS": "AXIS",
    "AXIS BANK": "AXIS",
    "KOTAK": "KOTAK",
    "KOTAK MAHINDRA BANK": "KOTAK",
    "PNB": "PNB",
    "PUNJAB NATIONAL BANK": "PNB",
    "BANK OF BARODA": "BOB",
    "BARODA": "BOB",
    "BOB": "BOB",
    "CANARA": "CANARA",
    "CANARA BANK": "CANARA",
    "UNION": "UNION",
    "UNION BANK": "UNION",
    "UNION BANK OF INDIA": "UNION",
    "INDIAN": "INDIAN",
    "INDIAN BANK": "INDIAN",
    "BOI": "BOI",
    "BANK OF INDIA": "BOI",
    "IDBI": "IDBI",
    "IDBI BANK": "IDBI",
    "INDUSIND": "INDUSIND",
    "INDUSIND BANK": "INDUSIND",
    "YES": "YES",
    "YES BANK": "YES",
    "FEDERAL": "FEDERAL",
    "FEDERAL BANK": "FEDERAL",
}

BANK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "SBI": ("state bank of india", "sbi"),
    "HDFC": ("hdfc bank", "hdfc"),
    "ICICI": ("icici bank", "icici"),
    "AXIS": ("axis bank", "axis"),
    "KOTAK": ("kotak mahindra bank", "kotak"),
    "PNB": ("punjab national bank", "pnb"),
    "BOB": ("bank of baroda", "bob", "baroda"),
    "CANARA": ("canara bank", "canara"),
    "UNION": ("union bank of india", "union bank", "union"),
    "INDIAN": ("indian bank", "indian bank ltd"),
    "BOI": ("bank of india", "boi"),
    "IDBI": ("idbi bank", "idbi"),
    "INDUSIND": ("indusind bank", "indusind"),
    "YES": ("yes bank", "yesbank", "yes bank ltd"),
    "FEDERAL": ("federal bank", "federal"),
}

ACCOUNT_TYPE_ALIASES: dict[str, str] = {
    "AUTO": "auto",
    "AUTO_DETECT": "auto",
    "BANK_ACCOUNT": "bank_account",
    "BANK STATEMENT": "bank_account",
    "BANK_STATEMENT": "bank_account",
    "SAVING": "bank_account",
    "SAVINGS": "bank_account",
    "CURRENT": "bank_account",
    "CREDIT_CARD": "credit_card",
    "CREDIT CARD": "credit_card",
    "CC": "credit_card",
}


@dataclass(frozen=True)
class ParserHints:
    bank_hint: str | None
    account_type_hint: str | None


def normalize_bank_hint(bank_hint: str | None) -> str | None:
    if not bank_hint:
        return None
    if not isinstance(bank_hint, str):
        return None
    raw = bank_hint.strip()
    if not raw:
        return None
    key = raw.upper().replace("-", " ").replace("_", " ")
    key = " ".join(key.split())
    return BANK_ALIASES.get(key, key)


def normalize_account_type_hint(account_type_hint: str | None) -> str | None:
    if not account_type_hint:
        return None
    if not isinstance(account_type_hint, str):
        return None
    raw = account_type_hint.strip()
    if not raw:
        return None
    key = raw.upper().replace("-", "_").replace(" ", "_")
    return ACCOUNT_TYPE_ALIASES.get(key, key.lower())


def normalize_parser_hints(
    bank_hint: str | None = None,
    account_type_hint: str | None = None,
) -> ParserHints:
    return ParserHints(
        bank_hint=normalize_bank_hint(bank_hint),
        account_type_hint=normalize_account_type_hint(account_type_hint),
    )


def infer_bank_hint_from_text(text: str) -> str | None:
    if not text:
        return None
    lower = _normalize_text(text)
    header = lower[:2500]
    scores: dict[str, int] = {}
    for bank, keywords in BANK_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in header:
                score += max(8, len(keyword.split()) * 6)
            elif keyword in lower:
                score += 1
        if score:
            scores[bank] = score
    if not scores:
        return None
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ranked[0][0]


def infer_account_type_hint_from_text(text: str) -> str | None:
    if not text:
        return None
    lower = _normalize_text(text)
    credit_card_cues = (
        "credit card",
        "card statement",
        "total amount due",
        "minimum amount due",
        "payment due date",
        "credit limit",
        "available limit",
        "card no",
    )
    if any(cue in lower for cue in credit_card_cues):
        return "credit_card"

    bank_account_cues = (
        "account statement",
        "savings account",
        "current account",
        "available balance",
        "closing balance",
        "opening balance",
        "withdrawal",
        "deposit",
        "cheque",
        "passbook",
    )
    if any(cue in lower for cue in bank_account_cues):
        return "bank_account"
    return None


def statement_keyword_tokens(text: str, *, limit: int = 80) -> set[str]:
    normalized = _normalize_text(text)
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]{3,}", normalized)
        if token not in _STOPWORDS and not token.isdigit()
    ]
    return set(tokens[:limit])


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "your",
    "bank",
    "statement",
    "account",
    "page",
    "date",
    "amount",
    "balance",
    "total",
    "credit",
    "debit",
    "transaction",
    "transactions",
    "description",
}
