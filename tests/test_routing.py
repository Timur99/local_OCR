from backend.app.pipeline import merge_pages
from backend.domain.models import EngineChoice, ProcessingPath, TriageResult
from backend.domain.routing import pages_for_ocr, processing_path


def test_text_based_pdf_skips_ocr() -> None:
    triage = TriageResult(pdf_type="text_based", confidence=0.9, page_count=3)
    assert pages_for_ocr(is_pdf=True, page_count=3, engine=EngineChoice.auto, triage=triage) == []


def test_mixed_pdf_ocr_only_listed_pages() -> None:
    triage = TriageResult(
        pdf_type="mixed",
        confidence=0.8,
        page_count=5,
        pages_needing_ocr=[2, 5],
    )
    assert pages_for_ocr(is_pdf=True, page_count=5, engine=EngineChoice.auto, triage=triage) == [2, 5]


def test_image_always_goes_to_ocr() -> None:
    assert pages_for_ocr(is_pdf=False, page_count=1, engine=EngineChoice.auto, triage=None) == [1]


def test_force_paddle_uses_all_pages() -> None:
    triage = TriageResult(pdf_type="text_based", confidence=1, page_count=2)
    assert pages_for_ocr(is_pdf=True, page_count=2, engine=EngineChoice.paddleocr, triage=triage) == [1, 2]


def test_auto_caps_ocr_pages_in_pipeline_constant() -> None:
    from backend.app.pipeline import MAX_AUTO_OCR_PAGES

    assert MAX_AUTO_OCR_PAGES <= 12


def test_merge_hybrid_pages() -> None:
    pages = merge_pages(
        page_count=2,
        native_by_page={1: "native page"},
        ocr_by_page={2: ("ocr page", 0.91)},
        ocr_pages=[2],
    )
    assert pages[0].source == ProcessingPath.native
    assert pages[1].source == ProcessingPath.ocr
    assert processing_path(True, True) == ProcessingPath.hybrid
