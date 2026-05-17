from pathlib import Path

FIXTURE_NAMES = {
    "bob_savings_sample.pdf",
    "hdfc_cc_sample.pdf",
    "icici_savings_sample.pdf",
    "corrupt.pdf",
    "image_only.pdf",
    "password_protected.pdf",
}


def test_synthetic_pdf_fixtures_exist():
    fixture_dir = Path(__file__).parents[1] / "fixtures"
    missing = [name for name in FIXTURE_NAMES if not (fixture_dir / name).exists()]
    assert not missing
