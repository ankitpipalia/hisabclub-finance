"""Tests for the Gmail sender-discovery scorer (Sprint C.1)."""

from __future__ import annotations

from app.engines.gmail.sender_discovery import (
    EmailEnvelope,
    discover_senders,
)


def test_known_bank_with_attachments_outscores_unknown():
    envelopes = [
        EmailEnvelope(
            from_address="alerts@hdfcbank.net",
            subject="HDFC Bank Credit Card Statement",
            has_attachment=True,
        ),
        EmailEnvelope(
            from_address="alerts@hdfcbank.net",
            subject="HDFC Bank Statement October",
            has_attachment=True,
        ),
        EmailEnvelope(
            from_address="newsletter@example.com",
            subject="Weekly digest",
            has_attachment=False,
        ),
    ]
    suggestions = discover_senders(envelopes)
    by_sender = {s.sender: s for s in suggestions}
    hdfc = by_sender["alerts@hdfcbank.net"]
    other = by_sender["newsletter@example.com"]

    assert hdfc.score > other.score
    assert hdfc.is_known_bank is True
    assert hdfc.attachment_count == 2
    assert hdfc.message_count == 2


def test_statement_keyword_bonus_applied():
    envelopes = [
        EmailEnvelope(
            from_address="payroll@employer.in",
            subject="Form 16 for FY 2024-25",
            has_attachment=True,
        ),
    ]
    suggestions = discover_senders(envelopes)
    assert suggestions[0].score >= 0.5  # known-bank=False, attach=0.3, keyword=0.25, vol=tiny


def test_allowlisted_senders_are_marked():
    envelopes = [
        EmailEnvelope(
            from_address="alerts@hdfcbank.net",
            subject="Statement",
            has_attachment=True,
        ),
    ]
    suggestions = discover_senders(
        envelopes, allowlisted_senders={"alerts@hdfcbank.net"}
    )
    assert suggestions[0].is_allowlisted is True


def test_sample_subjects_capped_at_three():
    envelopes = [
        EmailEnvelope(
            from_address="bank@x.com", subject=f"Subject {i}", has_attachment=False
        )
        for i in range(5)
    ]
    suggestions = discover_senders(envelopes)
    assert len(suggestions[0].sample_subjects) == 3


def test_top_n_limits_results():
    envelopes = [
        EmailEnvelope(
            from_address=f"sender{i}@x.com",
            subject="hi",
            has_attachment=False,
        )
        for i in range(20)
    ]
    suggestions = discover_senders(envelopes, top_n=5)
    assert len(suggestions) == 5


def test_empty_input_returns_empty_list():
    assert discover_senders([]) == []
