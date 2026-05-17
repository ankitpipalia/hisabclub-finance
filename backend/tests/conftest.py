from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def pytest_configure(config):
    fixture_dir = Path(__file__).parent / "fixtures"
    generator = fixture_dir / "generate_fixtures.py"
    bob = fixture_dir / "bob_savings_sample.pdf"
    if generator.exists() and not bob.exists():
        subprocess.run([sys.executable, str(generator)], check=True)
