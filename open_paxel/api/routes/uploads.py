from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from open_paxel.models.domain import ProcessingJobFileResult
from open_paxel.parser.auto import is_supported_transcript
from open_paxel.parser.patterns import SUPPORTED_TRANSCRIPT_SUFFIXES
from open_paxel.upload.worker import run_upload_job

logger = logging.getLogger(__name__)

router = APIRouter(tags=["uploads"])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
# Strong refs so background jobs aren't garbage-collected mid-run.
_background_jobs: set[asyncio.Task] = set()


class UploadFileResult(BaseModel):
    filename: str
    status: str
    session_id: str | None = None
    title: str | None = None
    error: str | None = None


class UploadJobResponse(BaseModel):
    job_id: str
    status: str
    total_count: int


class UploadResponse(BaseModel):
    upload_id: str | None = None
    session_count: int
    succeeded: int
    failed: int
    results: list[UploadFileResult]
    job_id: str | None = None


@router.get("/uploads")
def list_uploads(request: Request):
    return request.app.state.repository.list_uploads()


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, request: Request):
    repo = request.app.state.repository
    upload = repo.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    reports = [repo.get_report(sid) for sid in upload.session_ids]
    return {"upload": upload, "reports": [r for r in reports if r]}


@router.get("/jobs")
def list_jobs(request: Request, active: bool = False, limit: int = 20):
    repo = request.app.state.repository
    if active:
        return repo.list_active_jobs()
    return repo.list_jobs(limit=limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    job = request.app.state.repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def _save_upload_files(
    files: list[UploadFile],
    incoming_dir: Path,
) -> tuple[list[tuple[str, Path]], list[ProcessingJobFileResult]]:
    saved: list[tuple[str, Path]] = []
    skipped: list[ProcessingJobFileResult] = []

    for upload in files:
        filename = upload.filename or "unknown.txt"
        if not is_supported_transcript(filename):
            skipped.append(
                ProcessingJobFileResult(
                    filename=filename,
                    status="error",
                    error="Unsupported format. Use " + ", ".join(SUPPORTED_TRANSCRIPT_SUFFIXES),
                )
            )
            continue

        if upload.size and upload.size > MAX_UPLOAD_BYTES:
            skipped.append(
                ProcessingJobFileResult(
                    filename=filename,
                    status="error",
                    error=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                )
            )
            continue

        content = await upload.read()
        if not content.strip():
            skipped.append(
                ProcessingJobFileResult(
                    filename=filename,
                    status="error",
                    error="File is empty",
                )
            )
            continue

        dest = incoming_dir / f"{uuid.uuid4().hex}-{Path(filename).name}"
        dest.write_bytes(content)
        saved.append((filename, dest))
        logger.info("Saved upload %s → %s", filename, dest.name)

    return saved, skipped


@router.post("/upload")
async def upload_sessions(
    request: Request,
    files: list[UploadFile] = File(...),
    force: bool = False,
    sync: bool = False,
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    settings = request.app.state.settings
    repo = request.app.state.repository
    incoming_dir = settings.home / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)

    saved, skipped = await _save_upload_files(files, incoming_dir)
    total = len(saved) + len(skipped)

    if not saved and skipped:
        return UploadResponse(
            upload_id=None,
            session_count=0,
            succeeded=0,
            failed=len(skipped),
            results=[UploadFileResult.model_validate(r.model_dump()) for r in skipped],
        )

    job = repo.create_job(total_count=total, force=force, results=skipped)
    logger.info("Created processing job %s (%d files)", job.id, len(saved))

    if sync:
        await run_upload_job(
            job_id=job.id,
            files=saved,
            force=force,
            settings=settings,
            repo=repo,
        )
        job = repo.get_job(job.id)
        assert job is not None
        return UploadResponse(
            job_id=job.id,
            upload_id=job.upload_id,
            session_count=job.succeeded,
            succeeded=job.succeeded,
            failed=job.failed,
            results=[UploadFileResult.model_validate(r.model_dump()) for r in job.results],
        )

    task = asyncio.create_task(
        run_upload_job(
            job_id=job.id,
            files=saved,
            force=force,
            settings=settings,
            repo=repo,
        )
    )
    _background_jobs.add(task)
    task.add_done_callback(_background_jobs.discard)

    return JSONResponse(
        status_code=202,
        content=UploadJobResponse(
            job_id=job.id,
            status="queued",
            total_count=total,
        ).model_dump(),
    )
