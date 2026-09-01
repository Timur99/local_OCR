from backend.engines.base import OCREngine, OCRPageOutput
from backend.engines.paddle import PaddleOCREngine
from backend.engines.vision import AppleVisionEngine


def default_engines() -> list[OCREngine]:
    """Движки в порядке приоритета для режима «Авто».

    Vision первый: встроен в macOS, ничего не весит в бандле, в 16 раз быстрее
    PaddleOCR и лучше держит порядок чтения на многоколоночных страницах
    (замер 26.08.2026, см. `docs/DECISIONS.md`). PaddleOCR остаётся запасным —
    он работает не только на macOS и может оказаться сильнее на реальных фото,
    чего замер пока не проверял.
    """
    return [AppleVisionEngine(), PaddleOCREngine()]


__all__ = [
    "OCREngine",
    "OCRPageOutput",
    "PaddleOCREngine",
    "AppleVisionEngine",
    "default_engines",
]
