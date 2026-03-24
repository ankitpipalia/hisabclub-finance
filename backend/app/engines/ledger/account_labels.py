"""Helpers for consistent bank/account display labels."""


_ACCOUNT_TYPE_SUFFIX = {
    "credit_card": "CC",
    "savings": "Saving",
    "current": "Current",
    "salary": "Salary",
    "loan": "Loan",
    "demat": "Demat",
    "wallet": "Wallet",
    "upi": "UPI",
}

_BANK_DISPLAY_OVERRIDES = {
    "HDFC": "HDFC",
    "ICICI": "ICICI",
    "SBI": "SBI",
    "AXIS": "Axis",
    "KOTAK": "Kotak",
    "IDFC": "IDFC",
    "YES": "YES",
    "RBL": "RBL",
    "HSBC": "HSBC",
    "AMEX": "Amex",
}


def bank_account_label(bank_name: str | None, account_type: str | None) -> str | None:
    """Return display label like 'Kotak Saving', 'Kotak CC', etc."""
    if not bank_name and not account_type:
        return None

    bank = _display_bank_name(bank_name)
    account = _display_account_type(account_type)

    if bank and account:
        return f"{bank} {account}"
    return bank or account


def _display_bank_name(bank_name: str | None) -> str | None:
    if not bank_name:
        return None
    raw = bank_name.strip()
    if not raw:
        return None

    upper = raw.upper()
    if upper in _BANK_DISPLAY_OVERRIDES:
        return _BANK_DISPLAY_OVERRIDES[upper]

    # Preserve common acronyms while title-casing normal words.
    words = raw.replace("_", " ").split()
    formatted_words: list[str] = []
    for word in words:
        if len(word) <= 4 and word.isupper():
            formatted_words.append(word)
        else:
            formatted_words.append(word.capitalize())
    return " ".join(formatted_words)


def _display_account_type(account_type: str | None) -> str | None:
    if not account_type:
        return None
    normalized = account_type.strip().lower()
    if not normalized:
        return None
    return _ACCOUNT_TYPE_SUFFIX.get(normalized, normalized.replace("_", " ").title())
