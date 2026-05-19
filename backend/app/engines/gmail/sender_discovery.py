"""Sender-discovery wizard for the Gmail connector (Sprint C.1).

Reads a window of the user's inbox (envelopes only — no body fetch) and
scores each distinct sender on three signals:

  1. Known-bank-domain bonus — domains in `_KNOWN_BANK_DOMAINS`.
  2. Attachment-frequency bonus — count of messages with attachments.
  3. Statement-keyword bonus — subject contains "statement" / "account
     summary" / "form 16" / "tax" / "tds certificate" etc.

The result is a ranked list with allowlist status pulled from
`ConnectedAccount.allowed_senders`. The wizard UI then lets the user
one-click-add a sender to the allowlist.

This module is pure logic; the Gmail API call lives in `gmail.service`.
The wire-up endpoint is in `api/v1/gmail.py`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

_KNOWN_BANK_DOMAINS = (
    "hdfcbank.net",
    "hdfcbank.com",
    "alerts.hdfcbank.net",
    "icicibank.com",
    "alerts.icicibank.com",
    "billdesk.com",
    "axisbank.com",
    "sbi.co.in",
    "kotak.com",
    "yesbank.in",
    "indianbank.in",
    "pnb.co.in",
    "bankofbaroda.com",
    "bobcards.com",
    "cdslindia.com",
    "nsdl.co.in",
    "mfcentral.com",
    "kfintech.com",
    "camsonline.com",
    "incometax.gov.in",
    "incometaxindiaefiling.gov.in",
)

_STATEMENT_KEYWORDS = (
    "statement",
    "account summary",
    "credit card statement",
    "tds certificate",
    "form 16",
    "form-16",
    "form 26as",
    "interest certificate",
    "annual information statement",
    "ais",
    "tax",
    "demat",
    "consolidated account statement",
)

_DOMAIN_RE = re.compile(r"@([A-Za-z0-9.\-]+)")


@dataclass
class _SenderStats:
    sender: str  # full from-address (user-friendly display)
    domain: str
    message_count: int = 0
    attachment_count: int = 0
    statement_keyword_count: int = 0


@dataclass(frozen=True)
class SenderSuggestion:
    sender: str
    domain: str
    score: float  # 0.0..1.0
    message_count: int
    attachment_count: int
    is_known_bank: bool
    is_allowlisted: bool
    sample_subjects: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EmailEnvelope:
    """Minimal info we need to score a sender. Caller fetches via Gmail API."""

    from_address: str  # e.g. "alerts@hdfcbank.net"
    subject: str
    has_attachment: bool


def _extract_domain(from_address: str) -> str:
    match = _DOMAIN_RE.search(from_address.lower())
    return match.group(1) if match else ""


def _has_statement_keyword(subject: str) -> bool:
    lowered = subject.lower()
    return any(keyword in lowered for keyword in _STATEMENT_KEYWORDS)


def _score(stats: _SenderStats) -> float:
    """Combine the three signals into a 0..1 ranking score.

    Weights are chosen so a known-bank domain with attachments + statement
    keyword in subject sits near 1.0; an unknown sender with one stray email
    sits near 0.
    """
    base = 0.0
    # Attachment frequency: 0.3 per message with attachment, capped at 0.4.
    base += min(0.4, stats.attachment_count * 0.3)
    # Statement-keyword frequency: 0.25 per matching subject, capped at 0.35.
    base += min(0.35, stats.statement_keyword_count * 0.25)
    # Known-bank domain: flat 0.25.
    if stats.domain in _KNOWN_BANK_DOMAINS:
        base += 0.25
    # Volume tail: log-scaled bonus so a sender with 20 messages outranks
    # one with 2 (assuming other signals equal).
    if stats.message_count > 0:
        # min(0.15, log(n+1) / log(20)) → caps at 0.15 around 20 messages.
        from math import log

        base += min(0.15, log(stats.message_count + 1) / log(20))
    return round(min(1.0, base), 3)


def discover_senders(
    envelopes: Iterable[EmailEnvelope],
    *,
    allowlisted_senders: set[str] | None = None,
    top_n: int = 100,
) -> list[SenderSuggestion]:
    """Score and rank distinct senders. Returns at most `top_n` results.

    `allowlisted_senders` should be the current `ConnectedAccount.allowed_senders`
    so the UI can show "Already added" badges.
    """
    allowlisted = {s.lower() for s in (allowlisted_senders or set())}
    by_sender: dict[str, _SenderStats] = {}
    sample_subjects: dict[str, list[str]] = {}

    for env in envelopes:
        sender = env.from_address.strip()
        if not sender:
            continue
        key = sender.lower()
        if key not in by_sender:
            by_sender[key] = _SenderStats(
                sender=sender,
                domain=_extract_domain(sender),
            )
            sample_subjects[key] = []
        stats = by_sender[key]
        stats.message_count += 1
        if env.has_attachment:
            stats.attachment_count += 1
        if _has_statement_keyword(env.subject):
            stats.statement_keyword_count += 1
        if len(sample_subjects[key]) < 3:
            sample_subjects[key].append(env.subject)

    suggestions = [
        SenderSuggestion(
            sender=stats.sender,
            domain=stats.domain,
            score=_score(stats),
            message_count=stats.message_count,
            attachment_count=stats.attachment_count,
            is_known_bank=stats.domain in _KNOWN_BANK_DOMAINS,
            is_allowlisted=stats.sender.lower() in allowlisted,
            sample_subjects=tuple(sample_subjects[key]),
        )
        for key, stats in by_sender.items()
    ]
    suggestions.sort(
        key=lambda s: (-s.score, -s.message_count, s.domain, s.sender)
    )
    return suggestions[:top_n]


def domain_histogram(envelopes: Iterable[EmailEnvelope]) -> dict[str, int]:
    """Convenience: histogram of message count by domain (used in tests)."""
    counter: Counter[str] = Counter()
    for env in envelopes:
        counter[_extract_domain(env.from_address)] += 1
    return dict(counter)
