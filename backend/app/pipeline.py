from __future__ import annotations

from pathlib import Path

import fitz

from backend.domain.models import (
    EngineChoice,
    JobRecord,
    JobStatus,
    OCRResult,
    PageResult,
    ProcessingPath,
    TriageResult,
)
from backend.domain.routing import pages_for_ocr, processing_path
from backend.engines.base import OCREngine
from backend.infra.storage import JobStore
from backend.triage.inspector import inspect_pdf

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
PDF_SUFFIXES = {".pdf"}
MAX_RENDER_PAGES = 200
MAX_AUTO_OCR_PAGES = 12
RENDER_DPI = 120


class PipelineError(RuntimeError):
    pass


def render_pdf_page(pdf_path: Path, page_no: int, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    image_path = out_dir / f"page_{page_no:04d}.png"
    with fitz.open(pdf_path) as document:
        if page_no < 1 or page_no > document.page_count:
            raise PipelineError(f"Страница {page_no} вне диапазона 1..{document.page_count}")
        matrix = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
        document[page_no - 1].get_pixmap(matrix=matrix, alpha=False).save(image_path)
    return image_path


def merge_pages(
    *,
    page_count: int,
    native_by_page: dict[int, str],
    ocr_by_page: dict[int, tuple[str, float | None]],
    ocr_pages: list[int],
) -> list[PageResult]:
    pages: list[PageResult] = []
    ocr_set = set(ocr_pages)
    for page in range(1, page_count + 1):
        if page in ocr_set and page in ocr_by_page:
            text, confidence = ocr_by_page[page]
            pages.append(
                PageResult(
                    page=page,
                    source=ProcessingPath.ocr,
                    text=text,
                    markdown=text,
                    needs_ocr=True,
                    confidence=confidence,
                )
            )
            continue
        markdown = native_by_page.get(page, "")
        pages.append(
            PageResult(
                page=page,
                source=ProcessingPath.native,
                text=markdown,
                markdown=markdown,
                needs_ocr=False,
            )
        )
    return pages


class DocumentPipeline:
    def __init__(self, store: JobStore, ocr_engine: OCREngine) -> None:
        self.store = store
        self.ocr_engine = ocr_engine

    def run(self, job: JobRecord, source: Path) -> OCRResult:
        suffix = source.suffix.lower()
        is_pdf = suffix in PDF_SUFFIXES
        is_image = suffix in IMAGE_SUFFIXES
        if not is_pdf and not is_image:
            raise PipelineError("Поддерживаются PDF и изображения: JPG, PNG, WEBP, TIFF, BMP.")

        job.touch(JobStatus.preparing, 5, "Проверка файла")
        self.store.save(job)

        triage: TriageResult | None = None
        page_count = 1
        native_by_page: dict[int, str] = {}

        if is_pdf:
            job.touch(JobStatus.triaging, 15, "Классификация PDF")
            self.store.save(job)
            triage = inspect_pdf(source)
            page_count = triage.page_count
            native_by_page = triage.native_markdown_by_page
            if page_count > MAX_RENDER_PAGES:
                raise PipelineError(f"Слишком много страниц: {page_count}. Лимит MVP — {MAX_RENDER_PAGES}.")

        ocr_pages = pages_for_ocr(
            is_pdf=is_pdf,
            page_count=page_count,
            engine=job.engine,
            triage=triage,
        )
        if job.engine == EngineChoice.native:
            if is_image:
                raise PipelineError("Изображения нельзя обработать в режиме Native. Выберите Авто или PaddleOCR.")
            needs_ocr = bool(
                triage
                and (
                    triage.pdf_type in {"scanned", "image_based"}
                    or triage.pages_needing_ocr
                    or triage.has_encoding_issues
                )
            )
            if needs_ocr:
                raise PipelineError("Документ требует OCR. Выберите Авто или PaddleOCR.")

        ocr_by_page: dict[int, tuple[str, float | None]] = {}
        warnings = list(triage.warnings) if triage else []
        if job.engine == EngineChoice.auto and len(ocr_pages) > MAX_AUTO_OCR_PAGES:
            warnings.append(
                f"Авто-режим ограничивает OCR {MAX_AUTO_OCR_PAGES} страницами из {len(ocr_pages)}. "
                "Остальное оставлено native. Для полного OCR выберите PaddleOCR."
            )
            ocr_pages = ocr_pages[:MAX_AUTO_OCR_PAGES]

        if ocr_pages:
            if not self.ocr_engine.available():
                raise PipelineError(
                    "Нужен OCR, но PaddleOCR не установлен. "
                    "Для text-based PDF используйте режим Native или установите: pip install '.[ocr]'"
                )
            job.touch(JobStatus.running, 30, f"Подготовка OCR: {len(ocr_pages)} стр.")
            self.store.save(job)
            images: list[tuple[int, Path]] = []
            if is_image:
                images = [(1, source)]
            else:
                render_dir = self.store.job_dir(job.id) / "normalized"
                for page_no in ocr_pages:
                    images.append((page_no, render_pdf_page(source, page_no, render_dir)))

            def on_page(index: int, total: int, page: int) -> None:
                progress = 30 + int(50 * index / max(total, 1))
                job.touch(JobStatus.running, progress, f"OCR {index}/{total}: стр. {page}")
                self.store.save(job)

            for item in self.ocr_engine.recognize_images(images, job.language, on_page=on_page):
                ocr_by_page[item.page] = (item.text, item.confidence)
                warnings.extend(item.warnings)
            for _page_no, image_path in images:
                if image_path != source and image_path.exists():
                    image_path.unlink(missing_ok=True)

        job.touch(JobStatus.postprocessing, 85, "Сборка результата")
        self.store.save(job)

        pages = merge_pages(
            page_count=page_count,
            native_by_page=native_by_page,
            ocr_by_page=ocr_by_page,
            ocr_pages=ocr_pages,
        )
        used_native = any(page.source == ProcessingPath.native and page.markdown for page in pages)
        used_ocr = bool(ocr_by_page)
        markdown = "\n\n".join(page.markdown for page in pages if page.markdown).strip()
        text = "\n\n".join(page.text for page in pages if page.text).strip()
        engine_name = "native" if not used_ocr else self.ocr_engine.name
        if used_native and used_ocr:
            engine_name = f"pdf-inspector+{self.ocr_engine.name}"

        return OCRResult(
            text=text,
            markdown=markdown,
            pages=pages,
            path=processing_path(used_native, used_ocr),
            engine=engine_name,
            language=job.language,
            triage=triage,
            warnings=warnings,
            metadata={
                "filename": job.filename,
                "ocr_pages": ocr_pages,
                "page_count": page_count,
            },
        )
