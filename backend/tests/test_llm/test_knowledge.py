from types import SimpleNamespace

from app.engines.llm.knowledge import StatementKnowledgeContext, _rank_references


def test_statement_knowledge_context_formats_prompt_sections():
    context = StatementKnowledgeContext(
        recent_statement_summaries=["HDFC credit_card acct=XX1234 period=2026-02-01..2026-02-29 txns=42 parser=hdfc_cc_v1"],
        bank_candidates=["HDFC (3)"],
        account_type_candidates=["credit_card (3)"],
    )
    rendered = context.as_prompt_context()
    assert "Prior customer bank patterns" in rendered
    assert "Recent parsed statements" in rendered


def test_rank_references_prioritizes_bank_and_account_matches():
    chunks = [
        SimpleNamespace(
            chunk_hash_sha256="a",
            chunk_text="HDFC credit card total amount due minimum amount due reward points",
            bank_hint="HDFC",
            account_type_hint="credit_card",
            doc_type="credit_card_statement",
            source_filename="hdfc-cc.pdf",
            page_start=0,
            page_end=0,
        ),
        SimpleNamespace(
            chunk_hash_sha256="b",
            chunk_text="salary credit available balance cheque withdrawal branch",
            bank_hint="SBI",
            account_type_hint="bank_account",
            doc_type="bank_statement",
            source_filename="sbi-savings.pdf",
            page_start=0,
            page_end=0,
        ),
    ]

    ranked = _rank_references(
        chunks=chunks,
        tokens={"credit", "card", "amount", "due"},
        bank_hint="HDFC",
        account_type_hint="credit_card",
    )

    assert ranked
    assert ranked[0].source_filename == "hdfc-cc.pdf"
    assert ranked[0].score > ranked[-1].score
