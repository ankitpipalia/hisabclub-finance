from app.engines.ledger.nature import infer_transaction_nature


def test_credit_card_payment_credit_is_transfer_internal():
    nature = infer_transaction_nature(
        description_raw="PAYMENT RECEIVED - THANK YOU",
        direction="credit",
        account_type="credit_card",
    )
    assert nature == "transfer_internal"


def test_credit_card_cashback_is_refund():
    nature = infer_transaction_nature(
        description_raw="CASHBACK CREDIT FEB26-SMPOS:2~SMQR:82",
        direction="credit",
        account_type="credit_card",
    )
    assert nature == "refund"


def test_credit_card_merchant_credit_defaults_to_refund():
    nature = infer_transaction_nature(
        description_raw="AMAZON PAY INDIA PVT LTD BANGALORE",
        direction="credit",
        account_type="credit_card",
    )
    assert nature == "refund"


def test_salary_credit_is_income():
    nature = infer_transaction_nature(
        description_raw="SALARY CREDIT ACME PVT LTD",
        direction="credit",
        account_type="savings",
    )
    assert nature == "income"


def test_debit_credit_card_bill_payment_is_transfer_internal():
    nature = infer_transaction_nature(
        description_raw="IMPS SELF CREDIT CARD PAYMENT HDFC",
        direction="debit",
        account_type="savings",
    )
    assert nature == "transfer_internal"


def test_regular_debit_is_expense():
    nature = infer_transaction_nature(
        description_raw="SWIGGY ORDER #12345",
        direction="debit",
        account_type="credit_card",
    )
    assert nature == "expense"


def test_tele_transfer_credit_is_transfer_internal():
    nature = infer_transaction_nature(
        description_raw="TELE TRANSFER CREDIT",
        direction="credit",
        account_type="savings",
    )
    assert nature == "transfer_internal"
