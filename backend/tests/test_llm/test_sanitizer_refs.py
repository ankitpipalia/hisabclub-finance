from app.engines.llm.sanitizer import sanitize_for_llm


def test_sanitizer_preserves_upi_reference_ids() -> None:
    text = "UPI/123456789012/PHONEPE REF 123456789012 account 1234567890123"
    sanitized = sanitize_for_llm(text)

    assert "123456789012" in sanitized
    assert "XXXX-XXXX-XXXX-XXXX" in sanitized


def test_sanitizer_masks_explicit_account_number_context() -> None:
    text = "Account No 50100123456789 available balance 2300"
    sanitized = sanitize_for_llm(text)
    assert "XXXX-XXXX-XXXX-XXXX" in sanitized or "XXXX_ACCT" in sanitized
