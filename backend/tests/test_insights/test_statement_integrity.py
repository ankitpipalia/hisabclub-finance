from app.engines.insights.statement_integrity import evaluate_credit_card_integrity


def test_integrity_ok_when_net_activity_close_to_due() -> None:
    report = evaluate_credit_card_integrity(
        debit_total=120000,
        credit_total=20000,
        total_amount_due=100200,
        min_amount_due=5000,
        previous_balance=0,
        closing_balance=100100,
        transaction_count=42,
    )
    assert report.status == "ok"
    assert report.due_gap is not None and report.due_gap <= report.tolerance_due


def test_integrity_review_on_large_due_mismatch() -> None:
    report = evaluate_credit_card_integrity(
        debit_total=50000,
        credit_total=10000,
        total_amount_due=120000,
        min_amount_due=6000,
        previous_balance=0,
        closing_balance=120000,
        transaction_count=18,
    )
    assert report.status == "review"
    assert report.due_gap is not None and report.due_gap > report.tolerance_due
