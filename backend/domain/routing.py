from __future__ import annotations

from backend.domain.models import EngineChoice, ProcessingPath, TriageResult

# Явный выбор движка = принудительный OCR всех страниц, без оглядки на triage.
FORCED_OCR_ENGINES = {EngineChoice.vision, EngineChoice.paddleocr}


def pages_for_ocr(
    *,
    is_pdf: bool,
    page_count: int,
    engine: EngineChoice,
    triage: TriageResult | None,
) -> list[int]:
    """Return 1-indexed pages that should go through OCR."""
    if engine == EngineChoice.native:
        return []
    if not is_pdf:
        return list(range(1, max(page_count, 1) + 1))
    if engine in FORCED_OCR_ENGINES:
        return list(range(1, page_count + 1))
    if triage is None:
        return list(range(1, page_count + 1))
    if triage.has_encoding_issues and triage.pdf_type == "text_based":
        return list(range(1, page_count + 1))
    if triage.pdf_type in {"scanned", "image_based"}:
        return list(range(1, page_count + 1))
    return sorted(set(triage.pages_needing_ocr))


def ocr_reason(
    *,
    is_pdf: bool,
    engine: EngineChoice,
    triage: TriageResult | None,
) -> str:
    """Почему страница попала в план OCR.

    Ветки повторяют порядок `pages_for_ocr`: если меняешь одну функцию,
    меняй и вторую, иначе причина разойдётся с фактом.
    """
    if not is_pdf:
        return "image"
    if engine in FORCED_OCR_ENGINES:
        return "forced"
    if triage is None:
        return "no_triage"
    if triage.has_encoding_issues and triage.pdf_type == "text_based":
        return "encoding_issues"
    if triage.pdf_type in {"scanned", "image_based"}:
        return "scanned"
    return "no_text_layer"


def processing_path(used_native: bool, used_ocr: bool) -> ProcessingPath:
    if used_native and used_ocr:
        return ProcessingPath.hybrid
    if used_ocr:
        return ProcessingPath.ocr
    return ProcessingPath.native
