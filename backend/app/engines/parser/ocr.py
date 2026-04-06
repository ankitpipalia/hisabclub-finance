"""OCR helpers for scanned statement fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import settings
from app.engines.llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextQualityAssessment:
    total_pages: int
    empty_pages: int
    low_signal_pages: list[int] = field(default_factory=list)
    should_ocr: bool = False


@dataclass(frozen=True)
class OCRExtractionResult:
    pages: list[str]
    used_ocr: bool
    warnings: list[str] = field(default_factory=list)


def assess_text_quality(
    pages: list[str],
    *,
    min_chars: int | None = None,
    min_alpha_ratio: float | None = None,
) -> TextQualityAssessment:
    safe_min_chars = max(1, int(min_chars or settings.ocr_min_text_chars_per_page))
    safe_min_alpha_ratio = float(
        min_alpha_ratio if min_alpha_ratio is not None else settings.ocr_min_alpha_ratio
    )
    empty_pages = 0
    low_signal_pages: list[int] = []

    for index, page in enumerate(pages):
        normalized = " ".join((page or "").split())
        if not normalized:
            empty_pages += 1
            low_signal_pages.append(index)
            continue
        alpha_count = sum(1 for char in normalized if char.isalpha())
        signal_ratio = alpha_count / max(1, len(normalized))
        if len(normalized) < safe_min_chars or signal_ratio < safe_min_alpha_ratio:
            low_signal_pages.append(index)

    total_pages = len(pages)
    should_ocr = total_pages == 0 or empty_pages == total_pages
    if total_pages and len(low_signal_pages) >= max(1, total_pages // 2):
        should_ocr = True

    return TextQualityAssessment(
        total_pages=total_pages,
        empty_pages=empty_pages,
        low_signal_pages=low_signal_pages,
        should_ocr=should_ocr,
    )


async def extract_text_with_ocr_fallback(
    *,
    pdf_bytes: bytes,
    text_pages: list[str],
    client: LLMClient | None,
    model: str | None = None,
) -> OCRExtractionResult:
    assessment = assess_text_quality(text_pages)
    if client is None or not settings.ocr_enabled or not assessment.low_signal_pages:
        return OCRExtractionResult(pages=text_pages, used_ocr=False)

    target_pages = assessment.low_signal_pages[: max(1, settings.ocr_page_limit)]
    rendered_pages = render_pdf_pages(pdf_bytes, target_pages, dpi=settings.ocr_render_dpi)
    if not rendered_pages:
        return OCRExtractionResult(
            pages=text_pages,
            used_ocr=False,
            warnings=["OCR fallback could not render low-signal pages."],
        )

    merged_pages = list(text_pages)
    replaced = 0
    warnings: list[str] = []
    for page_index, image_bytes in rendered_pages:
        prompt = (
            "Transcribe this Indian financial statement page to plain text only. "
            "Preserve reading order, dates, amounts, DR/CR markers, and line items. "
            "Do not summarize. Do not add commentary. Return only the page text."
        )
        text = await client.chat_vision(
            prompt,
            image_bytes=image_bytes,
            max_tokens=3200,
            temperature=0.0,
            timeout_sec=settings.ocr_timeout_sec,
            max_attempts=settings.ocr_max_attempts,
            model=model,
        )
        normalized = (text or "").strip()
        if not normalized:
            warnings.append(f"OCR returned empty output for page {page_index + 1}.")
            continue
        merged_pages[page_index] = normalized
        replaced += 1

    if replaced == 0:
        return OCRExtractionResult(
            pages=text_pages,
            used_ocr=False,
            warnings=warnings or ["OCR fallback did not improve page text."],
        )

    warnings.insert(
        0,
        f"OCR fallback transcribed {replaced} low-signal page(s) using local vision OCR.",
    )
    logger.info("OCR fallback replaced %d page(s)", replaced)
    return OCRExtractionResult(pages=merged_pages, used_ocr=True, warnings=warnings)


def render_pdf_pages(
    pdf_bytes: bytes,
    page_indexes: list[int],
    *,
    dpi: int,
) -> list[tuple[int, bytes]]:
    if not page_indexes:
        return []

    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    rendered: list[tuple[int, bytes]] = []
    try:
        scale = max(1.0, float(dpi) / 72.0)
        matrix = fitz.Matrix(scale, scale)
        for page_index in page_indexes:
            if page_index < 0 or page_index >= len(doc):
                continue
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            rendered.append((page_index, pix.tobytes("png")))
    finally:
        doc.close()
    return rendered
