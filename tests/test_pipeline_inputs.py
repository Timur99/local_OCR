from pathlib import Path

import pytest

from backend.domain.models import EngineChoice, JobRecord
from backend.domain.routing import pages_for_ocr
from backend.triage.inspector import inspect_pdf

INPUTS = Path(__file__).resolve().parents[1] / "inputs"


def _pdfs() -> list[Path]:
    if not INPUTS.exists():
        return []
    return sorted(path for path in INPUTS.iterdir() if path.suffix.lower() == ".pdf")


@pytest.mark.skipif(not _pdfs(), reason="inputs/ с PDF отсутствует")
def test_inspector_classifies_sample_pdfs() -> None:
    reports = []
    for path in _pdfs():
        triage = inspect_pdf(path)
        ocr_pages = pages_for_ocr(
            is_pdf=True,
            page_count=triage.page_count,
            engine=EngineChoice.auto,
            triage=triage,
        )
        reports.append(
            {
                "file": path.name,
                "type": triage.pdf_type,
                "pages": triage.page_count,
                "ocr_pages": ocr_pages,
                "native_pages": len(triage.native_markdown_by_page),
            }
        )
        assert triage.page_count >= 1
        assert 0 <= triage.confidence <= 1
        assert all(page >= 1 for page in ocr_pages)
    assert reports


@pytest.mark.skipif(not _pdfs(), reason="inputs/ с PDF отсутствует")
def test_native_path_extracts_text_from_digital_pdf() -> None:
    from backend.app.pipeline import DocumentPipeline
    from backend.engines.paddle import PaddleOCREngine
    from backend.infra.storage import JobStore

    digital = None
    for path in _pdfs():
        triage = inspect_pdf(path)
        if triage.pdf_type == "text_based" and not triage.pages_needing_ocr:
            digital = path
            break
    if digital is None:
        pytest.skip("Среди inputs нет полностью text-based PDF")

    store = JobStore(Path("data/test-jobs"))
    pipeline = DocumentPipeline(store, PaddleOCREngine())
    job = JobRecord(id="test-native", filename=digital.name, engine=EngineChoice.auto)
    result = pipeline.run(job, digital)
    assert result.path.value == "native"
    assert result.text
    assert result.metadata["ocr_pages"] == []
