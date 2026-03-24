from app.engines.insights.tax_compliance import (
    _calculate_new_regime_tax,
    build_tax_action_items,
)


def test_tax_action_items_warn_on_missing_docs_and_parser_backlog() -> None:
    totals = {
        "interest_income": 12000.0,
        "dividend_income": 2000.0,
        "tax_payments": 5000.0,
        "other_income": 60000.0,
    }
    coverage = {
        "tax_form": 0,
        "interest_certificate": 0,
        "dividend_report": 0,
        "tax_challan": 0,
    }

    items = build_tax_action_items(
        totals=totals,
        coverage=coverage,
        unresolved_statement_docs=3,
        high_value_cash_expense_count=2,
    )
    titles = {item["title"] for item in items}

    assert "Missing Tax Forms" in titles
    assert "Interest Income Without Certificate" in titles
    assert "Dividend Income Without Report" in titles
    assert "Tax Payments Without Challan" in titles
    assert "Review Other Income" in titles
    assert "High-Value Cash Transactions" in titles
    assert "Unresolved Statement Parsers" in titles


def test_tax_action_items_returns_ok_when_no_flags() -> None:
    items = build_tax_action_items(
        totals={
            "interest_income": 0.0,
            "dividend_income": 0.0,
            "tax_payments": 0.0,
            "other_income": 1000.0,
        },
        coverage={
            "tax_form": 2,
            "interest_certificate": 1,
            "dividend_report": 1,
            "tax_challan": 1,
        },
        unresolved_statement_docs=0,
        high_value_cash_expense_count=0,
    )

    assert len(items) == 1
    assert items[0]["severity"] == "ok"


def test_new_regime_tax_fy_2024_rebate_zeroes_tax_at_7l() -> None:
    calc = _calculate_new_regime_tax(estimated_taxable_income=700000, fy_start_year=2024)
    assert calc["new_regime_tax_before_rebate"] == 20000.0
    assert calc["new_regime_rebate"] == 20000.0
    assert calc["new_regime_total_tax"] == 0.0


def test_new_regime_tax_fy_2025_marginal_relief_near_12l() -> None:
    calc = _calculate_new_regime_tax(estimated_taxable_income=1250000, fy_start_year=2025)
    assert calc["new_regime_tax_before_rebate"] == 67500.0
    assert calc["new_regime_rebate"] == 17500.0
    assert calc["new_regime_tax_after_rebate"] == 50000.0
    assert calc["new_regime_cess"] == 2000.0
    assert calc["new_regime_total_tax"] == 52000.0
