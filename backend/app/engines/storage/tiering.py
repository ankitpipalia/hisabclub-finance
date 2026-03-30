"""Hot/cold storage tiering for uploaded statement PDFs."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone

from app.config import settings
from app.models.raw_pdf import RawPdf


def move_raw_pdf_to_cold_tier(raw_pdf: RawPdf) -> bool:
    """Move a PDF from hot upload path to cold archive path.

    Returns True when move succeeded and metadata was updated.
    """
    if not settings.cold_storage_enabled:
        return False
    if raw_pdf.storage_tier == "cold":
        return False

    src = raw_pdf.storage_path
    if not src or not os.path.exists(src):
        return False

    month_bucket = datetime.now(timezone.utc).strftime("%Y-%m")
    destination_dir = os.path.join(
        settings.cold_storage_dir,
        str(raw_pdf.user_id),
        month_bucket,
    )
    os.makedirs(destination_dir, exist_ok=True)
    dst = os.path.join(destination_dir, os.path.basename(src))

    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.move(src, dst)

    raw_pdf.cold_storage_path = dst
    raw_pdf.storage_path = dst
    raw_pdf.storage_tier = "cold"
    return True

