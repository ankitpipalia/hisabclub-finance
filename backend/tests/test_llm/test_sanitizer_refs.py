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


def test_sanitizer_preserves_standalone_12_digit_ref_when_flag_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.engines.llm.sanitizer.settings.sanitizer_preserve_short_refs", True)
    text = "Payment received with reference 987654321234 for invoice."

    sanitized = sanitize_for_llm(text)

    assert "987654321234" in sanitized


def test_sanitizer_masks_16_digit_card_with_wider_context_when_flag_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.engines.llm.sanitizer.settings.sanitizer_preserve_short_refs", True)
    text = "Card ending number 4111111111111111."

    sanitized = sanitize_for_llm(text)

    assert "4111111111111111" not in sanitized
    assert "XXXX-XXXX-XXXX-XXXX" in sanitized


def test_sanitizer_preserves_16_digit_ref_without_account_context_when_flag_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.engines.llm.sanitizer.settings.sanitizer_preserve_short_refs", True)
    text = "Standalone batch reference 4111111111111111 reconciled."

    sanitized = sanitize_for_llm(text)

    assert "4111111111111111" in sanitized
