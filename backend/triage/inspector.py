from __future__ import annotations

from pathlib import Path

from backend.domain.models import TriageResult


def inspect_pdf(path: Path) -> TriageResult:
    import pdf_inspector

    detected = pdf_inspector.detect_pdf(str(path))
    pages = pdf_inspector.extract_pages_markdown(str(path))
    native: dict[int, str] = {}
    for page in pages.pages:
        page_no = page.page + 1
        if page.needs_ocr:
            continue
        markdown = (page.markdown or "").strip()
        if markdown:
            native[page_no] = markdown

    warnings: list[str] = []
    if getattr(detected, "has_encoding_issues", False):
        warnings.append("Обнаружены проблемы кодировки шрифтов — страницы могут уйти в OCR.")
    if getattr(detected, "is_complex_layout", False):
        warnings.append("Сложный layout: таблицы или несколько колонок.")

    return TriageResult(
        pdf_type=detected.pdf_type,
        confidence=float(detected.confidence or 0.0),
        page_count=int(detected.page_count),
        pages_needing_ocr=list(detected.pages_needing_ocr or []),
        native_markdown_by_page=native,
        has_encoding_issues=bool(getattr(detected, "has_encoding_issues", False)),
        is_complex_layout=bool(getattr(detected, "is_complex_layout", False)),
        pages_with_tables=list(getattr(detected, "pages_with_tables", []) or []),
        warnings=warnings,
        processing_time_ms=int(getattr(detected, "processing_time_ms", 0) or 0),
    )
