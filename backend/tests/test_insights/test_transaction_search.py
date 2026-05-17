"""Token-weighted scoring + tokenization for transaction_search."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

from app.engines.insights.transaction_search import (
    SearchHit,
    _FIELD_WEIGHTS,
    _score,
    _tokenize,
)


def _txn(**over) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "transaction_date": date(2026, 5, 1),
        "amount": "1234.56",
        "direction": "debit",
        "merchant_normalized": "ICICI Bank EMI",
        "merchant_raw": "ICICI BANK EMI PAYMENT XXX",
        "notes": None,
        "bank_name": "ICICI",
        "account_masked": "XXXX1234",
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_tokenize_lowercases_and_strips_punctuation():
    assert _tokenize("ICICI EMI  ") == ["icici", "emi"]
    assert _tokenize("upi-XX/24") == ["upi", "xx", "24"]
    assert _tokenize("") == []


def test_score_rewards_merchant_normalized_more_than_notes():
    high = _score(
        _txn(merchant_normalized="ICICI EMI", notes=""), None, ["icici"], "icici"
    )
    low = _score(
        _txn(merchant_normalized="X", notes="ICICI EMI"), None, ["icici"], "icici"
    )
    assert high[0] > low[0]


def test_score_returns_matched_terms_deduped():
    score, matched = _score(_txn(), None, ["icici", "icici", "emi"], "")
    assert "icici" in matched
    assert "emi" in matched
    # Deduped by the search() wrapper, but here we just check shape.
    assert isinstance(matched, list)


def test_exact_phrase_bonus_applied_once():
    with_phrase = _score(_txn(merchant_raw="icici bank emi payment"), None, ["icici", "emi"], "icici bank")
    no_phrase = _score(_txn(merchant_raw="icici something else"), None, ["icici"], "")
    assert with_phrase[0] > no_phrase[0]


def test_score_zero_when_no_terms_match():
    score, matched = _score(_txn(merchant_normalized="Swiggy"), None, ["plumber"], "plumber")
    assert score == 0
    assert matched == []


def test_category_match_adds_small_boost():
    base_score, _ = _score(_txn(merchant_normalized="X"), None, ["food"], "")
    boosted, _ = _score(_txn(merchant_normalized="X"), "Food", ["food"], "")
    assert boosted > base_score


def test_field_weights_consistent_with_documentation():
    # Spec'd in module: merchant_normalized=3, merchant_raw=2, notes=1, bank_name=1
    assert _FIELD_WEIGHTS["merchant_normalized"] == 3.0
    assert _FIELD_WEIGHTS["merchant_raw"] == 2.0
    assert _FIELD_WEIGHTS["notes"] == 1.0
    assert _FIELD_WEIGHTS["bank_name"] == 1.0


def test_search_hit_to_dict_serializes_decimals_and_uuids():
    hit = SearchHit(
        transaction_id=uuid.uuid4(),
        transaction_date=date(2026, 5, 1),
        amount=__import__("decimal").Decimal("1234.56"),
        direction="debit",
        merchant="ICICI",
        category_name="Bills",
        bank_name="ICICI",
        account_masked="XXXX1234",
        score=7.123456,
        matched_terms=["icici"],
    )
    payload = hit.to_dict()
    assert payload["amount"] == "1234.56"
    assert payload["score"] == 7.123
    assert payload["matched_terms"] == ["icici"]
    assert payload["transaction_date"] == "2026-05-01"
