from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class OCRPageOutput:
    page: int
    text: str
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)


class OCREngine(Protocol):
    name: str

    def available(self) -> bool: ...
    def recognize_images(self, images: list[tuple[int, Path]], language: str) -> list[OCRPageOutput]: ...
