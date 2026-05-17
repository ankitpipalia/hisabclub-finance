"""Generate deterministic synthetic PDF fixtures for parser/pipeline tests.

No real financial data is used. Run from backend/: python tests/fixtures/generate_fixtures.py
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUTPUT_DIR = os.path.dirname(__file__)


def make_statement_pdf(
    filename: str,
    bank_name: str,
    account_number: str,
    period_start: date,
    period_end: date,
    opening_balance: Decimal,
    transactions: list[dict],
    password: str | None = None,
) -> str:
    path = os.path.join(OUTPUT_DIR, filename)
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 60, bank_name)
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, f"Account: {account_number}")
    c.drawString(50, height - 95, f"Period: {period_start} to {period_end}")
    c.drawString(50, height - 110, f"Opening Balance: {opening_balance:,.2f}")

    y = height - 140
    c.setFont("Helvetica-Bold", 9)
    for label, x in [
        ("Date", 50),
        ("Description", 120),
        ("Debit", 320),
        ("Credit", 400),
        ("Balance", 470),
    ]:
        c.drawString(x, y, label)
    c.line(50, y - 5, width - 50, y - 5)

    c.setFont("Helvetica", 9)
    running = opening_balance
    for txn in transactions:
        y -= 18
        amount = Decimal(str(txn["amount"]))
        running = running + amount if txn["is_credit"] else running - amount
        balance = Decimal(str(txn.get("balance_after", running)))
        c.drawString(50, y, str(txn["date"]))
        c.drawString(120, y, txn["description"][:35])
        if txn["is_credit"]:
            c.drawString(400, y, f"{amount:,.2f}")
        else:
            c.drawString(320, y, f"{amount:,.2f}")
        c.drawString(470, y, f"{balance:,.2f}")

    y -= 30
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, f"Closing Balance: {running:,.2f}")
    c.save()

    if password:
        _encrypt_pdf(path, password)
    return path


def _encrypt_pdf(path: str, password: str) -> None:
    try:
        import pikepdf

        encrypted_path = f"{path}.encrypted"
        with pikepdf.open(path) as pdf:
            pdf.save(
                encrypted_path,
                encryption=pikepdf.Encryption(owner=password, user=password, R=4),
            )
        os.replace(encrypted_path, path)
    except ImportError:
        return


COMMON_TXNS = [
    {
        "date": date(2024, 1, 3),
        "description": "NEFT CR SALARY",
        "amount": "50000.00",
        "is_credit": True,
    },
    {
        "date": date(2024, 1, 5),
        "description": "UPI/SWIGGY ORDER",
        "amount": "340.00",
        "is_credit": False,
    },
    {
        "date": date(2024, 1, 10),
        "description": "ATM WDL HDFC BANK",
        "amount": "5000.00",
        "is_credit": False,
    },
    {
        "date": date(2024, 1, 15),
        "description": "NEFT DR RENT",
        "amount": "15000.00",
        "is_credit": False,
    },
    {
        "date": date(2024, 1, 28),
        "description": "INTEREST CREDIT",
        "amount": "312.50",
        "is_credit": True,
    },
]


if __name__ == "__main__":
    make_statement_pdf(
        "bob_savings_sample.pdf",
        "Bank of Baroda",
        "****1234",
        date(2024, 1, 1),
        date(2024, 1, 31),
        Decimal("10000.00"),
        COMMON_TXNS,
    )
    make_statement_pdf(
        "hdfc_cc_sample.pdf",
        "HDFC Bank Credit Card",
        "****5678",
        date(2024, 1, 1),
        date(2024, 1, 31),
        Decimal("0.00"),
        [
            {
                "date": date(2024, 1, 4),
                "description": "AMAZON.IN",
                "amount": "1299.00",
                "is_credit": False,
            },
            {
                "date": date(2024, 1, 9),
                "description": "ZOMATO",
                "amount": "450.00",
                "is_credit": False,
            },
            {
                "date": date(2024, 1, 20),
                "description": "PAYMENT THK",
                "amount": "5000.00",
                "is_credit": True,
            },
        ],
    )
    make_statement_pdf(
        "icici_savings_sample.pdf",
        "ICICI Bank",
        "****9012",
        date(2024, 1, 1),
        date(2024, 1, 31),
        Decimal("25000.00"),
        COMMON_TXNS,
    )
    with open(os.path.join(OUTPUT_DIR, "corrupt.pdf"), "wb") as handle:
        handle.write(b"%PDF-1.4\n" + b"\x00\xff\x00" * 100)

    c = canvas.Canvas(os.path.join(OUTPUT_DIR, "image_only.pdf"), pagesize=A4)
    c.setFillGray(0.9)
    c.rect(100, 200, 300, 300, fill=1)
    c.save()

    make_statement_pdf(
        "password_protected.pdf",
        "SBI Bank",
        "****3456",
        date(2024, 1, 1),
        date(2024, 1, 31),
        Decimal("8000.00"),
        COMMON_TXNS[:2],
        password="test1234",
    )
    print(f"Fixtures generated in {OUTPUT_DIR}")
