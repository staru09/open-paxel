from __future__ import annotations

import uuid
from pathlib import Path

from open_paxel.db.models import (
    ProcessingJobRow,
    ProfileRow,
    SessionReportRow,
    UploadRow,
    init_db,
    make_engine,
)
from open_paxel.models.domain import (
    BuilderProfile,
    ProcessingJob,
    ProcessingJobFileResult,
    SessionReport,
    UploadReport,
    utcnow,
)
from open_paxel.models.pipeline_models import PipelineArtifacts
from open_paxel.profile.aggregate import build_profile


class SQLiteRepository:
    def __init__(self, db_path: Path):
        self.engine = make_engine(str(db_path))
        self.Session = init_db(self.engine)

    def save_report(self, report: SessionReport) -> None:
        with self.Session() as session:
            row = SessionReportRow(
                session_id=report.session_id,
                transcript_path=report.transcript_path,
                project_path=report.project_path,
                title=report.title,
                analyzed_at=report.analyzed_at,
                report_json=report.model_dump(mode="json"),
                upload_id=report.upload_id,
            )
            session.merge(row)
            session.commit()

    def get_report(self, session_id: str) -> SessionReport | None:
        with self.Session() as session:
            row = session.get(SessionReportRow, session_id)
            if not row:
                return None
            return SessionReport.model_validate(row.report_json)

    def update_report_title(self, session_id: str, title: str) -> SessionReport | None:
        cleaned = title.strip()
        with self.Session() as session:
            row = session.get(SessionReportRow, session_id)
            if not row:
                return None
            report = SessionReport.model_validate(row.report_json)
            report = report.model_copy(update={"title": cleaned or None})
            row.title = report.title
            row.report_json = report.model_dump(mode="json")
            session.commit()
        self.refresh_profile()
        return report

    def list_reports(self, limit: int = 100, offset: int = 0) -> list[SessionReport]:
        with self.Session() as session:
            rows = (
                session.query(SessionReportRow)
                .order_by(SessionReportRow.analyzed_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [SessionReport.model_validate(r.report_json) for r in rows]

    def report_exists(self, session_id: str) -> bool:
        with self.Session() as session:
            return session.get(SessionReportRow, session_id) is not None

    def create_upload(self, session_ids: list[str], project_paths: list[str]) -> UploadReport:
        upload_id = str(uuid.uuid4())
        upload = UploadReport(
            id=upload_id,
            created_at=utcnow(),
            session_count=len(session_ids),
            project_paths=sorted(set(project_paths)),
            session_ids=session_ids,
        )
        with self.Session() as session:
            session.add(
                UploadRow(
                    id=upload.id,
                    created_at=upload.created_at,
                    session_count=upload.session_count,
                    project_paths=upload.project_paths,
                    session_ids=upload.session_ids,
                )
            )
            for sid in session_ids:
                row = session.get(SessionReportRow, sid)
                if row:
                    row.upload_id = upload_id
            session.commit()
        return upload

    def get_upload(self, upload_id: str) -> UploadReport | None:
        with self.Session() as session:
            row = session.get(UploadRow, upload_id)
            if not row:
                return None
            return UploadReport(
                id=row.id,
                created_at=row.created_at,
                session_count=row.session_count,
                project_paths=row.project_paths,
                session_ids=row.session_ids,
                pipeline_artifacts=(
                    PipelineArtifacts.model_validate(row.pipeline_json)
                    if row.pipeline_json
                    else None
                ),
            )

    def list_uploads(self) -> list[UploadReport]:
        with self.Session() as session:
            rows = session.query(UploadRow).order_by(UploadRow.created_at.desc()).all()
            return [
                UploadReport(
                    id=r.id,
                    created_at=r.created_at,
                    session_count=r.session_count,
                    project_paths=r.project_paths,
                    session_ids=r.session_ids,
                    pipeline_artifacts=(
                        PipelineArtifacts.model_validate(r.pipeline_json)
                        if r.pipeline_json
                        else None
                    ),
                )
                for r in rows
            ]

    def save_upload_artifacts(self, upload_id: str, artifacts: PipelineArtifacts) -> None:
        with self.Session() as session:
            row = session.get(UploadRow, upload_id)
            if not row:
                return
            row.pipeline_json = artifacts.model_dump(mode="json")
            session.commit()

    def _cached_profile(self) -> BuilderProfile | None:
        with self.Session() as session:
            cached = session.get(ProfileRow, 1)
            return BuilderProfile.model_validate(cached.profile_json) if cached else None

    def get_profile(self) -> BuilderProfile:
        return self._cached_profile() or self.refresh_profile()

    def refresh_profile(self) -> BuilderProfile:
        """Rebuild the heuristic profile outside a batch run.

        Keeps the LLM narrative and pipeline artifacts from the last batch; the next
        upload regenerates them.
        """
        profile = build_profile(self.list_reports(limit=10_000), self.list_uploads())
        if cached := self._cached_profile():
            profile = profile.model_copy(
                update={
                    "narrative": cached.narrative,
                    "pipeline_artifacts": cached.pipeline_artifacts,
                }
            )
        self.save_profile_cache(profile)
        return profile

    def save_profile_cache(self, profile: BuilderProfile) -> None:
        with self.Session() as session:
            session.merge(
                ProfileRow(
                    id=1,
                    updated_at=profile.updated_at,
                    profile_json=profile.model_dump(mode="json"),
                )
            )
            session.commit()

    def clear_ephemeral_state(self) -> int:
        """Remove in-flight upload jobs (ephemeral testing mode)."""
        with self.Session() as session:
            deleted = session.query(ProcessingJobRow).delete()
            session.commit()
            return deleted

    def _row_to_job(self, row: ProcessingJobRow) -> ProcessingJob:
        return ProcessingJob(
            id=row.id,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            force=bool(row.force),
            total_count=row.total_count,
            succeeded=row.succeeded,
            failed=row.failed,
            current_file=row.current_file,
            current_step=row.current_step,
            results=[ProcessingJobFileResult.model_validate(r) for r in (row.results_json or [])],
            upload_id=row.upload_id,
            logs=list(row.logs_json or []),
            openai_calls=list(row.openai_calls_json or []),
        )

    def create_job(
        self,
        *,
        total_count: int,
        force: bool = False,
        results: list[ProcessingJobFileResult] | None = None,
    ) -> ProcessingJob:
        job_id = str(uuid.uuid4())
        now = utcnow()
        initial_results = [r.model_dump(mode="json") for r in (results or [])]
        row = ProcessingJobRow(
            id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
            force=force,
            total_count=total_count,
            succeeded=sum(1 for r in (results or []) if r.status == "ok"),
            failed=sum(1 for r in (results or []) if r.status == "error"),
            results_json=initial_results,
            logs_json=[f"Job created with {total_count} file(s)"],
        )
        with self.Session() as session:
            session.add(row)
            session.commit()
        return self._row_to_job(row)

    def get_job(self, job_id: str) -> ProcessingJob | None:
        with self.Session() as session:
            row = session.get(ProcessingJobRow, job_id)
            if not row:
                return None
            return self._row_to_job(row)

    def list_active_jobs(self) -> list[ProcessingJob]:
        with self.Session() as session:
            rows = (
                session.query(ProcessingJobRow)
                .filter(ProcessingJobRow.status.in_(("queued", "processing")))
                .order_by(ProcessingJobRow.created_at.desc())
                .all()
            )
            return [self._row_to_job(r) for r in rows]

    def list_jobs(self, limit: int = 20) -> list[ProcessingJob]:
        with self.Session() as session:
            rows = (
                session.query(ProcessingJobRow)
                .order_by(ProcessingJobRow.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._row_to_job(r) for r in rows]

    def append_openai_call(self, job_id: str, call: dict) -> None:
        with self.Session() as session:
            row = session.get(ProcessingJobRow, job_id)
            if not row:
                return
            calls = list(row.openai_calls_json or [])
            calls.append(call)
            row.openai_calls_json = calls[-200:]
            row.updated_at = utcnow()
            session.commit()

    def append_job_log(self, job_id: str, message: str) -> None:
        with self.Session() as session:
            row = session.get(ProcessingJobRow, job_id)
            if not row:
                return
            logs = list(row.logs_json or [])
            logs.append(message)
            row.logs_json = logs[-100:]
            row.updated_at = utcnow()
            session.commit()

    def update_job(self, job_id: str, **fields) -> None:
        with self.Session() as session:
            row = session.get(ProcessingJobRow, job_id)
            if not row:
                return
            if "results" in fields:
                results = fields.pop("results")
                row.results_json = [r.model_dump(mode="json") for r in results]
            for key, value in fields.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = utcnow()
            session.commit()
