from __future__ import annotations

from pathlib import Path

from backend.app.pipeline import DocumentPipeline
from backend.engines.paddle import PaddleOCREngine
from backend.infra.storage import JobStore

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path.cwd() / "data" / "jobs"
MAX_UPLOAD_BYTES = 80 * 1024 * 1024

store = JobStore(DATA_DIR)
pipeline = DocumentPipeline(store, PaddleOCREngine())
