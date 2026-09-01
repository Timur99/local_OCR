from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    preparing = "preparing"
    triaging = "triaging"
    running = "running"
    postprocessing = "postprocessing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EngineChoice(str, Enum):
    auto = "auto"
    native = "native"
    vision = "vision"
    paddleocr = "paddleocr"


class ProcessingPath(str, Enum):
    native = "native"
    ocr = "ocr"
    hybrid = "hybrid"


class PageResult(BaseModel):
    page: int
    source: ProcessingPath
    text: str = ""
    markdown: str = ""
    needs_ocr: bool = False
    # Почему страница попала в план OCR: image | forced | scanned |
    # encoding_issues | no_text_layer | no_triage. None — страница взята напрямую.
    ocr_reason: str | None = None
    # Почему запланированный OCR не состоялся: limit | failed.
    # None — состоялся (или не планировался).
    skipped_reason: str | None = None
    confidence: float | None = None


class TriageResult(BaseModel):
    pdf_type: str
    confidence: float
    page_count: int
    pages_needing_ocr: list[int] = Field(default_factory=list)
    native_markdown_by_page: dict[int, str] = Field(default_factory=dict)
    has_encoding_issues: bool = False
    is_complex_layout: bool = False
    pages_with_tables: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processing_time_ms: int = 0


class OCRResult(BaseModel):
    text: str = ""
    markdown: str = ""
    pages: list[PageResult] = Field(default_factory=list)
    path: ProcessingPath = ProcessingPath.native
    engine: str = "native"
    language: str = "ru"
    triage: TriageResult | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    id: str
    status: JobStatus = JobStatus.queued
    filename: str
    engine: EngineChoice = EngineChoice.auto
    language: str = "ru"
    progress: int = 0
    message: str = "В очереди"
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    result: OCRResult | None = None

    def touch(
        self,
        status: JobStatus | None = None,
        progress: int | None = None,
        message: str | None = None,
    ) -> None:
        if status is not None:
            self.status = status
        if progress is not None:
            self.progress = max(0, min(100, progress))
        if message is not None:
            self.message = message
        self.updated_at = datetime.now(timezone.utc)
