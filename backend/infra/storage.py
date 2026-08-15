from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from backend.domain.models import JobRecord


SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    cleaned = SAFE_NAME.sub("_", Path(name).name).strip("._")
    return (cleaned or "upload")[:80]


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()

    def create(self, filename: str, data: bytes, **kwargs) -> tuple[JobRecord, Path]:
        job_id = uuid4().hex
        job_dir = self.root / job_id
        source_dir = job_dir / "source"
        source_dir.mkdir(parents=True)
        path = source_dir / safe_filename(filename)
        path.write_bytes(data)
        job = JobRecord(id=job_id, filename=filename, **kwargs)
        with self._lock:
            self._jobs[job_id] = job
        self._write_meta(job)
        return job, path

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[JobRecord]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def save(self, job: JobRecord) -> None:
        with self._lock:
            self._jobs[job.id] = job
        self._write_meta(job)
        if job.result is not None:
            result_dir = self.root / job.id / "result"
            result_dir.mkdir(parents=True, exist_ok=True)
            (result_dir / "result.json").write_text(
                job.result.model_dump_json(indent=2),
                encoding="utf-8",
            )
            (result_dir / "result.md").write_text(job.result.markdown or job.result.text, encoding="utf-8")
            (result_dir / "result.txt").write_text(job.result.text, encoding="utf-8")

    def delete(self, job_id: str) -> bool:
        with self._lock:
            existed = self._jobs.pop(job_id, None) is not None
        job_dir = self.root / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
            return True
        return existed

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def _write_meta(self, job: JobRecord) -> None:
        meta = job.model_dump(mode="json", exclude={"result"})
        path = self.root / job.id / "job.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
