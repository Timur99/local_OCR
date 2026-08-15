from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from backend.app.context import MAX_UPLOAD_BYTES, pipeline, store
from backend.domain.models import EngineChoice, JobRecord, JobStatus

router = APIRouter(prefix="/api/v1")

ALLOWED_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp")


def _public_job(job: JobRecord) -> dict:
    payload = job.model_dump(mode="json", exclude={"result"})
    if job.result is not None:
        payload["path"] = job.result.path.value
        payload["engine_used"] = job.result.engine
        payload["page_count"] = job.result.metadata.get("page_count")
        payload["ocr_pages"] = job.result.metadata.get("ocr_pages", [])
        payload["pdf_type"] = job.result.triage.pdf_type if job.result.triage else None
    return payload


def _run_job(job_id: str, path: Path) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        result = pipeline.run(job, path)
        job.result = result
        job.touch(JobStatus.completed, 100, "Готово")
        store.save(job)
    except Exception as exc:
        job.error = str(exc)
        job.touch(JobStatus.failed, job.progress, "Ошибка")
        store.save(job)


@router.get("/engines")
def engines() -> dict:
    return {
        "default": EngineChoice.auto.value,
        "engines": [
            {
                "id": "auto",
                "label": "Авто",
                "available": True,
                "description": "pdf-inspector, OCR только для проблемных страниц",
            },
            {
                "id": "native",
                "label": "Только native",
                "available": True,
                "description": "Без OCR. Только text-based PDF",
            },
            {
                "id": "paddleocr",
                "label": "PaddleOCR",
                "available": pipeline.ocr_engine.available(),
                "description": "Принудительный OCR всех страниц",
            },
        ],
    }


@router.post("/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    engine: EngineChoice = Form(EngineChoice.auto),
    language: str = Form("ru"),
) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Файл больше лимита {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    filename = file.filename or "upload"
    if not filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(415, "Поддерживаются PDF и изображения")

    job, path = store.create(filename, data, engine=engine, language=language)
    job.touch(JobStatus.queued, 1, "Файл принят, обработка в фоне")
    store.save(job)
    background_tasks.add_task(_run_job, job.id, path)
    return _public_job(job)


@router.get("/jobs")
def list_jobs() -> dict:
    return {"jobs": [_public_job(job) for job in store.list()]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Задача не найдена")
    return _public_job(job)


@router.get("/jobs/{job_id}/result")
def get_result(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Задача не найдена")
    if job.status == JobStatus.failed:
        raise HTTPException(422, job.error or "Ошибка обработки")
    if job.result is None:
        raise HTTPException(409, "Результат ещё не готов")
    return job.result.model_dump(mode="json")


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    if not store.delete(job_id):
        raise HTTPException(404, "Задача не найдена")
    return {"deleted": job_id}
