import uuid
from datetime import date

from app.engines.insights.reconciliation import TransferCandidate, pair_transfer_candidates


def _candidate(
    amount: float,
    direction: str,
    txn_date: date,
    bank: str | None,
    account_type: str | None,
) -> TransferCandidate:
    return TransferCandidate(
        id=uuid.uuid4(),
        transaction_date=txn_date,
        amount=amount,
        direction=direction,
        transaction_nature="transfer_internal",
        merchant_raw="TEST TRANSFER",
        bank_name=bank,
        account_type=account_type,
        account_masked=None,
        source_files=[],
    )


def test_pair_transfer_candidates_matches_cross_bank_amounts() -> None:
    debit = _candidate(1000, "debit", date(2025, 3, 10), "HDFC", "savings")
    credit = _candidate(1000, "credit", date(2025, 3, 11), "AXIS", "credit_card")
    unmatched_debit = _candidate(750, "debit", date(2025, 3, 14), "HDFC", "savings")

    pairs, unmatched = pair_transfer_candidates([debit, credit, unmatched_debit], max_gap_days=5)

    assert len(pairs) == 1
    assert pairs[0]["amount"] == 1000
    assert pairs[0]["day_gap"] == 1
    assert pairs[0]["debit"]["id"] == str(debit.id)
    assert pairs[0]["credit"]["id"] == str(credit.id)
    assert len(unmatched) == 1
    assert unmatched[0].id == unmatched_debit.id
