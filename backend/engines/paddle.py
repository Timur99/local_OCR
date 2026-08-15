from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from backend.engines.base import OCRPageOutput


def _collect_text(value: Any, texts: list[str], scores: list[float]) -> None:
    if isinstance(value, dict):
        rec_texts = value.get("rec_texts")
        rec_scores = value.get("rec_scores")
        if isinstance(rec_texts, list):
            texts.extend(str(item) for item in rec_texts if item)
            if isinstance(rec_scores, list):
                scores.extend(float(item) for item in rec_scores if item is not None)
            return
        for child in value.values():
            _collect_text(child, texts, scores)
        return
    if isinstance(value, list):
        if (
            len(value) == 2
            and isinstance(value[1], (list, tuple))
            and value[1]
            and isinstance(value[1][0], str)
        ):
            texts.append(value[1][0])
            if len(value[1]) > 1 and isinstance(value[1][1], (int, float)):
                scores.append(float(value[1][1]))
            return
        for child in value:
            _collect_text(child, texts, scores)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    for attr in ("json", "to_json", "to_dict"):
        candidate = getattr(value, attr, None)
        if candidate is None:
            continue
        candidate = candidate() if callable(candidate) else candidate
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                return candidate
        return _to_jsonable(candidate)
    return str(value)


class PaddleOCREngine:
    name = "paddleocr"

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def available(self) -> bool:
        return importlib.util.find_spec("paddleocr") is not None

    def recognize_images(
        self,
        images: list[tuple[int, Path]],
        language: str,
        on_page: Callable[[int, int, int], None] | None = None,
    ) -> list[OCRPageOutput]:
        if not self.available():
            raise RuntimeError(
                "PaddleOCR не установлен. Для OCR-страниц выполните: pip install '.[ocr]'"
            )
        client = self._client(language)
        outputs: list[OCRPageOutput] = []
        total = len(images)
        for index, (page, image) in enumerate(images, start=1):
            if on_page is not None:
                on_page(index, total, page)
            raw = self._run(client, image)
            texts: list[str] = []
            scores: list[float] = []
            _collect_text(_to_jsonable(raw), texts, scores)
            outputs.append(
                OCRPageOutput(
                    page=page,
                    text="\n".join(texts).strip(),
                    confidence=round(sum(scores) / len(scores), 4) if scores else None,
                )
            )
        return outputs

    def _client(self, language: str) -> Any:
        lang = "ru" if language.startswith("ru") else language
        if lang not in self._clients:
            from paddleocr import PaddleOCR

            try:
                self._clients[lang] = PaddleOCR(
                    lang=lang,
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except TypeError:
                self._clients[lang] = PaddleOCR(lang=lang, use_angle_cls=False)
        return self._clients[lang]

    def _run(self, client: Any, image: Path) -> Any:
        try:
            return list(client.predict(str(image)))
        except TypeError:
            return client.ocr(str(image), cls=True)
