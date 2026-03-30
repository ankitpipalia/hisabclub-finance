from app.models.statement import normalize_statement_parse_status


def test_normalize_statement_parse_status_maps_legacy_values():
    assert normalize_statement_parse_status("no_transactions") == "partial"
    assert normalize_statement_parse_status("success") == "parsed"
    assert normalize_statement_parse_status("parsing") == "extracting"


def test_normalize_statement_parse_status_handles_unknown_value():
    assert normalize_statement_parse_status("unexpected_status") == "failed"


def test_normalize_statement_parse_status_defaults_when_empty():
    assert normalize_statement_parse_status("") == "uploaded"
    assert normalize_statement_parse_status(None) == "uploaded"
