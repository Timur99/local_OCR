"""Командная строка PDF2Text.

Общая база для обеих оболочек: Tauri-sidecar и MCP-сервер запускают пайплайн
без окна, и обоим нужен один и тот же headless-вход.

Прогресс идёт в stderr, результат — в stdout, чтобы `pdf2text scan.pdf > out.md`
работал без мусора в файле.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from backend.app.pipeline import DocumentPipeline, PipelineError
from backend.domain.models import EngineChoice, JobRecord
from backend.engines import default_engines
from backend.infra.storage import JobStore

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


class ProgressStore(JobStore):
    """JobStore, который вместо истории задач печатает прогресс в stderr.

    В CLI нет ни сайдбара, ни поллинга: документ пользователя не должен
    оставаться на диске после выхода, поэтому корень — временный каталог.
    """

    def __init__(self, root: Path, quiet: bool) -> None:
        super().__init__(root)
        self.quiet = quiet
        self._last = ""

    def save(self, job: JobRecord) -> None:  # noqa: D102
        super().save(job)
        if self.quiet or job.message == self._last:
            return
        self._last = job.message
        print(f"  {job.progress:>3}%  {job.message}", file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2text",
        description="Извлекает текст из PDF и изображений локально. Файл никуда не отправляется.",
    )
    parser.add_argument("file", type=Path, help="PDF или изображение")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Куда записать результат. По умолчанию — stdout.",
    )
    parser.add_argument(
        "-e",
        "--engine",
        choices=[choice.value for choice in EngineChoice],
        default=EngineChoice.auto.value,
        help="auto — OCR только там, где он нужен (по умолчанию); "
        "native — без OCR; paddleocr — OCR всех страниц.",
    )
    parser.add_argument("-l", "--lang", default="ru", help="Язык распознавания (по умолчанию ru)")
    parser.add_argument(
        "-f",
        "--format",
        choices=["md", "txt", "json"],
        default="md",
        help="Формат вывода (по умолчанию md)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Не печатать прогресс")
    return parser


def render(result, fmt: str) -> str:
    if fmt == "json":
        return result.model_dump_json(indent=2)
    if fmt == "txt":
        return result.text
    return result.markdown or result.text


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source: Path = args.file.expanduser()
    if not source.is_file():
        print(f"Файл не найден: {source}", file=sys.stderr)
        return EXIT_USAGE

    workdir = Path(tempfile.mkdtemp(prefix="pdf2text-"))
    try:
        store = ProgressStore(workdir / "jobs", quiet=args.quiet)
        pipeline = DocumentPipeline(store, default_engines())
        job = JobRecord(
            id="cli",
            filename=source.name,
            engine=EngineChoice(args.engine),
            language=args.lang,
        )
        try:
            result = pipeline.run(job, source)
        except PipelineError as exc:
            print(f"Ошибка: {exc}", file=sys.stderr)
            return EXIT_ERROR

        for warning in result.warnings:
            print(f"  ! {warning}", file=sys.stderr)

        payload = render(result, args.format)
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
            if not args.quiet:
                skipped = result.metadata.get("skipped_pages") or []
                tail = f", не распознано страниц: {len(skipped)}" if skipped else ""
                print(
                    f"  Готово: {args.output} ({result.path.value}, {result.engine}{tail})",
                    file=sys.stderr,
                )
        else:
            try:
                sys.stdout.write(payload)
                if not payload.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.flush()
            except BrokenPipeError:
                # `pdf2text file.pdf | head` закрывает поток раньше нас.
                # Перенаправляем stdout в /dev/null, иначе финальный flush
                # интерпретатора выбросит ту же ошибку уже после main().
                os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return EXIT_OK
    finally:
        # Документ пользователя и промежуточные PNG не должны пережить процесс.
        shutil.rmtree(workdir, ignore_errors=True)


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()
