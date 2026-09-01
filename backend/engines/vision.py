"""Apple Vision — OCR, встроенный в macOS.

Ноль мегабайт в бандле: модели уже стоят у каждого пользователя Mac. Замер
26.08.2026 (см. `docs/DECISIONS.md`): тот же объём текста, что у PaddleOCR,
в 16 раз быстрее и с правильным порядком чтения на многоколоночных страницах.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

from backend.engines.base import OCRPageOutput

# Языки, которые Vision понимает (macOS 15.4, revision 3). Ключ — наш код языка.
VISION_LANGUAGES = {
    "ru": "ru-RU",
    "uk": "uk-UA",
    "en": "en-US",
    "de": "de-DE",
    "fr": "fr-FR",
    "it": "it-IT",
    "es": "es-ES",
    "pt": "pt-BR",
    "zh": "zh-Hans",
    "ko": "ko-KR",
    "ja": "ja-JP",
    "th": "th-TH",
    "vi": "vi-VT",
    "ar": "ar-SA",
}


def vision_languages(language: str) -> list[str]:
    """Список языков для `setRecognitionLanguages_`, в порядке приоритета.

    Английский добавляем всегда: в русских документах постоянно попадаются
    латинские термины, а без него Vision пытается прочитать их кириллицей.
    """
    code = language.split("-")[0].lower()
    primary = VISION_LANGUAGES.get(code)
    if primary is None:
        return ["en-US"]
    return [primary] if primary == "en-US" else [primary, "en-US"]


class AppleVisionEngine:
    name = "vision"

    def available(self) -> bool:
        if sys.platform != "darwin":
            return False
        return all(importlib.util.find_spec(module) is not None for module in ("Vision", "Quartz"))

    def recognize_images(
        self,
        images: list[tuple[int, Path]],
        language: str,
        on_page: Callable[[int, int, int], None] | None = None,
    ) -> list[OCRPageOutput]:
        if not self.available():
            raise RuntimeError(
                "Apple Vision недоступен. Нужна macOS и: pip install '.[vision]'"
            )
        import Quartz
        import Vision
        from Foundation import NSURL

        languages = vision_languages(language)
        outputs: list[OCRPageOutput] = []
        total = len(images)
        for index, (page, image) in enumerate(images, start=1):
            if on_page is not None:
                on_page(index, total, page)
            text, confidence, warnings = self._recognize(Quartz, Vision, NSURL, image, languages)
            outputs.append(
                OCRPageOutput(page=page, text=text, confidence=confidence, warnings=warnings)
            )
        return outputs

    def _recognize(
        self, Quartz: Any, Vision: Any, NSURL: Any, image: Path, languages: list[str]
    ) -> tuple[str, float | None, list[str]]:
        url = NSURL.fileURLWithPath_(str(image.resolve()))
        # Именно CGImageSource: initWithURL_options_ на связке pyobjc отдаёт
        # "zero-dimensioned image" даже на корректном файле.
        source = Quartz.CGImageSourceCreateWithURL(url, None)
        if source is None:
            return "", None, [f"Vision не смог прочитать изображение страницы {image.name}"]
        cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
        if cg_image is None:
            return "", None, [f"Vision не смог декодировать страницу {image.name}"]

        request = Vision.VNRecognizeTextRequest.alloc().init()
        # Accurate — это 0, Fast — 1. Не перепутать.
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setRecognitionLanguages_(languages)
        request.setUsesLanguageCorrection_(True)

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            return "", None, [f"Vision вернул ошибку на странице {image.name}: {error}"]

        # Порядок наблюдений Vision не трогаем: на многоколоночных страницах он
        # держит колонки вместе, а сортировка по координатам это сломает.
        lines: list[str] = []
        scores: list[float] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue
            lines.append(str(candidates[0].string()))
            scores.append(float(candidates[0].confidence()))

        confidence = round(sum(scores) / len(scores), 4) if scores else None
        return "\n".join(lines), confidence, []
