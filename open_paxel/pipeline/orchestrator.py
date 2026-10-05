from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import contextmanager

from open_paxel.analysis.context import emit_progress
from open_paxel.config import Settings
from open_paxel.git.reader import code_quality_label, link_commits_to_session, read_git_log
from open_paxel.models.pipeline_models import PipelineArtifacts
from open_paxel.pipeline.context import PipelineContext
from open_paxel.pipeline.steps.decisions import (
    aggregate_decisions,
    enrich_catalog_fields,
    link_decision_outcomes,
    redact_decisions,
)
from open_paxel.pipeline.steps.work_streams import build_work_streams
from open_paxel.scorer.decision_classifier import classify_decisions
from open_paxel.scorer.episode_scorer import score_episode

logger = logging.getLogger(__name__)

STEP_LABELS = [
    "Discovering project and sessions",
    "Reading git history",
    "Linking git commits by session",
    "Grouping work streams",
    "Extracting decision exchanges",
    "Redacting decisions",
    "Linking decisions to outcomes",
    "Analyzing code quality",
    "Scoring episodes",
    "Assembling profile",
]


class PaxelPipeline:
    def __init__(self, settings: Settings, repository):
        self.settings = settings
        self.repository = repository

    def _save(self, report) -> None:
        if not self.settings.dry_run:
            self.repository.save_report(report)

    async def run_batch(
        self,
        ctx: PipelineContext,
        *,
        set_step: Callable[[str], None] | None = None,
    ) -> PipelineArtifacts:
        labels = iter(STEP_LABELS)
        timings: list[tuple[str, float]] = []

        @contextmanager
        def stage():
            label = next(labels)
            msg = f"Step {len(timings) + 1}/{len(STEP_LABELS)}: {label}"
            if set_step:
                set_step(msg)
            emit_progress(msg)
            t0 = time.perf_counter()
            yield
            timings.append((label, time.perf_counter() - t0))

        with stage():  # project path (discovery itself happens before the batch)
            if ctx.repo:
                ctx.project_path = ctx.repo.path
            elif not ctx.project_path and ctx.reports:
                ctx.project_path = ctx.reports[0].project_path

        with stage():
            if ctx.project_path:
                ctx.git_commits = read_git_log(ctx.project_path)

        with stage():
            ctx.reports = [
                r.model_copy(
                    update={
                        "git_commit_ids": link_commits_to_session(
                            ctx.git_commits, started_at=r.started_at, ended_at=r.ended_at
                        )
                    }
                )
                for r in ctx.reports
            ]
            for report in ctx.reports:
                self._save(report)

        with stage():
            ctx.work_streams = build_work_streams(
                ctx.reports,
                gap_hours=self.settings.work_stream_gap_hours,
            )
            by_id = ctx.reports_by_id()
            for stream in ctx.work_streams:
                stream.git_commit_ids = sorted(
                    {
                        commit
                        for sid in stream.session_ids
                        if sid in by_id
                        for commit in by_id[sid].git_commit_ids
                    }
                )

        # Steering traces are attached per session in AnalysisPipeline.analyze_file.
        with stage():
            ctx.decisions = await classify_decisions(ctx.reports, self.settings)

        with stage():
            ctx.decisions = redact_decisions(ctx.decisions)

        with stage():
            ctx.decisions = link_decision_outcomes(ctx.decisions, ctx.reports_by_id())
            ctx.decisions = enrich_catalog_fields(ctx.decisions)
            ctx.reports = [
                r.model_copy(
                    update={"decisions": [d for d in ctx.decisions if d.session_id == r.session_id]}
                )
                for r in ctx.reports
            ]
            for report in ctx.reports:
                self._save(report)

        with stage():
            if ctx.project_path:
                ctx.code_quality_label = code_quality_label(ctx.project_path)

        with stage():
            decision_summaries = [d.summary for d in ctx.decisions if d.summary]
            ctx.episodes = [
                await score_episode(
                    stream,
                    ctx.reports,
                    settings=self.settings,
                    code_quality_label=ctx.code_quality_label,
                    decision_summaries=decision_summaries,
                )
                for stream in ctx.work_streams
            ]

        with stage():
            if not self.settings.dry_run:
                from open_paxel.profile.assembler import assemble_profile

                await assemble_profile(self.settings, self.repository, ctx)

        agg = aggregate_decisions(ctx.decisions)
        emit_progress(
            f"Pipeline complete: {len(ctx.reports)} sessions, "
            f"{len(ctx.decisions)} decisions, {len(ctx.episodes)} episodes "
            f"(top pattern: {agg.get('top_catalog_title') or 'none'})"
        )
        for label, elapsed in timings:
            emit_progress(f"  ✓ {elapsed:.1f}s  {label}")

        return ctx.artifacts()
