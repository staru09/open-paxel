from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from pathlib import Path

from open_paxel.analysis.context import AnalysisJobContext, OpenAICallRecord, format_openai_log
from open_paxel.models.domain import ProcessingJobFileResult
from open_paxel.pipeline.analysis import AnalysisPipeline
from open_paxel.pipeline.context import PipelineContext
from open_paxel.pipeline.orchestrator import PaxelPipeline

logger = logging.getLogger(__name__)


async def run_upload_job(
    *,
    job_id: str,
    files: list[tuple[str, Path]],
    force: bool,
    settings,
    repo,
    repo_info=None,
) -> None:
    """Background worker: analyze saved files and run Paxel batch pipeline."""
    pipeline = AnalysisPipeline(settings, repo)
    paxel = PaxelPipeline(settings, repo)
    outcomes: list[ProcessingJobFileResult] = []
    ok_reports = []

    def log(msg: str) -> None:
        logger.info("job=%s %s", job_id[:8], msg)
        repo.append_job_log(job_id, msg)

    def set_step(step: str) -> None:
        repo.update_job(job_id, current_step=step)

    def on_openai_call(record: OpenAICallRecord) -> None:
        payload = asdict(record)
        repo.append_openai_call(job_id, payload)
        if record.status != "started":
            log(format_openai_log(record))

    ctx = AnalysisJobContext(
        log_progress=log,
        set_step=set_step,
        on_openai_call=on_openai_call,
    )

    try:
        with ctx:
            repo.update_job(
                job_id,
                status="processing",
                current_step="Starting analysis",
                current_file=None,
            )
            log(f"Processing {len(files)} file(s) with model {settings.effective_model()}")

            sem = asyncio.Semaphore(settings.concurrency)

            async def analyze_one(original_name: str, path: Path) -> None:
                async with sem:
                    repo.update_job(
                        job_id,
                        current_file=original_name,
                        current_step="Parsing transcript",
                    )
                    log(f"Analyzing {original_name}")
                    try:
                        report = await pipeline.analyze_file(path, force=force)
                        ok_reports.append(report)
                        result = ProcessingJobFileResult(
                            filename=original_name,
                            status="ok",
                            session_id=report.session_id,
                            title=report.title,
                        )
                        outcomes.append(result)
                        repo.update_job(
                            job_id,
                            succeeded=len([r for r in outcomes if r.status == "ok"]),
                            failed=len([r for r in outcomes if r.status == "error"]),
                            results=outcomes,
                        )
                        log(f"Completed {original_name} → {report.title or report.session_id[:8]}")
                    except Exception as exc:
                        logger.exception("job=%s failed file=%s", job_id[:8], original_name)
                        result = ProcessingJobFileResult(
                            filename=original_name,
                            status="error",
                            error=str(exc),
                        )
                        outcomes.append(result)
                        repo.update_job(
                            job_id,
                            succeeded=len([r for r in outcomes if r.status == "ok"]),
                            failed=len([r for r in outcomes if r.status == "error"]),
                            results=outcomes,
                        )
                        log(f"Failed {original_name}: {exc}")

            await asyncio.gather(*(analyze_one(name, path) for name, path in files))

        upload_id: str | None = None
        if ok_reports:
            project_paths = sorted({r.project_path for r in ok_reports if r.project_path})
            upload = repo.create_upload(
                [r.session_id for r in ok_reports],
                project_paths,
            )
            upload_id = upload.id
            log(f"Upload batch created id={upload_id[:8]}")

            pipe_ctx = PipelineContext(
                repo=repo_info,
                reports=ok_reports,
                project_path=project_paths[0] if project_paths else None,
                upload_id=upload_id,
            )
            await paxel.run_batch(pipe_ctx, set_step=set_step)

        succeeded = sum(1 for r in outcomes if r.status == "ok")
        failed = sum(1 for r in outcomes if r.status == "error")
        final_status = "completed" if succeeded else "failed"
        if succeeded and failed:
            final_status = "completed"

        repo.update_job(
            job_id,
            status=final_status,
            current_file=None,
            current_step="Done",
            succeeded=succeeded,
            failed=failed,
            results=outcomes,
            upload_id=upload_id,
        )
        log(f"Job finished: {succeeded} succeeded, {failed} failed")
    except Exception as exc:
        logger.exception("job=%s crashed", job_id[:8])
        repo.append_job_log(job_id, f"Job crashed: {exc}")
        repo.update_job(
            job_id,
            status="failed",
            current_step="Job failed",
            results=outcomes,
        )
