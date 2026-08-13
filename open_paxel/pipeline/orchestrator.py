from __future__ import annotations

import logging
import time
from collections.abc import Callable

from open_paxel.analysis.context import emit_progress
from open_paxel.config import Settings
from open_paxel.discover.scanner import discover_repo_for_cwd
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
    "Extracting steering traces",
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

    async def run_batch(
        self,
        ctx: PipelineContext,
        *,
        set_step: Callable[[str], None] | None = None,
    ) -> PipelineArtifacts:
        total = len(STEP_LABELS)
        timings: list[tuple[str, float]] = []

        def step(n: int, label: str) -> None:
            msg = f"Step {n}/{total}: {label}"
            if set_step:
                set_step(msg)
            emit_progress(msg)

        # Step 1 — discover (usually done before batch; ensure project path)
        t0 = time.perf_counter()
        step(1, STEP_LABELS[0])
        if ctx.repo:
            ctx.project_path = ctx.repo.path
        elif not ctx.project_path and ctx.reports:
            ctx.project_path = ctx.reports[0].project_path
        timings.append((STEP_LABELS[0], time.perf_counter() - t0))

        # Step 2 — git history
        t0 = time.perf_counter()
        step(2, STEP_LABELS[1])
        if ctx.project_path:
            ctx.git_commits = read_git_log(ctx.project_path)
        timings.append((STEP_LABELS[1], time.perf_counter() - t0))

        # Step 3 — link commits to sessions
        t0 = time.perf_counter()
        step(3, STEP_LABELS[2])
        updated_reports = []
        for report in ctx.reports:
            commit_ids = link_commits_to_session(
                ctx.git_commits,
                started_at=report.started_at,
                ended_at=report.ended_at,
            )
            updated = report.model_copy(update={"git_commit_ids": commit_ids})
            updated_reports.append(updated)
            if not self.settings.dry_run:
                self.repository.save_report(updated)
        ctx.reports = updated_reports
        timings.append((STEP_LABELS[2], time.perf_counter() - t0))

        # Step 4 — work streams
        t0 = time.perf_counter()
        step(4, STEP_LABELS[3])
        ctx.work_streams = build_work_streams(
            ctx.reports,
            gap_hours=self.settings.work_stream_gap_hours,
        )
        for stream in ctx.work_streams:
            ids = set()
            for sid in stream.session_ids:
                report = ctx.reports_by_id().get(sid)
                if report:
                    ids.update(report.git_commit_ids)
            stream.git_commit_ids = sorted(ids)
        timings.append((STEP_LABELS[3], time.perf_counter() - t0))

        # Step 5 — steering traces (already on reports from analyze_file)
        t0 = time.perf_counter()
        step(5, STEP_LABELS[4])
        timings.append((STEP_LABELS[4], time.perf_counter() - t0))

        # Step 6 — decisions LLM
        t0 = time.perf_counter()
        step(6, STEP_LABELS[5])
        ctx.decisions = await classify_decisions(ctx.reports, self.settings)
        timings.append((STEP_LABELS[5], time.perf_counter() - t0))

        # Step 7 — redact
        t0 = time.perf_counter()
        step(7, STEP_LABELS[6])
        ctx.decisions = redact_decisions(ctx.decisions)
        timings.append((STEP_LABELS[6], time.perf_counter() - t0))

        # Step 8 — link outcomes
        t0 = time.perf_counter()
        step(8, STEP_LABELS[7])
        ctx.decisions = link_decision_outcomes(ctx.decisions, ctx.reports_by_id())
        ctx.decisions = enrich_catalog_fields(ctx.decisions)
        for report in ctx.reports:
            session_decisions = [d for d in ctx.decisions if d.session_id == report.session_id]
            updated = report.model_copy(update={"decisions": session_decisions})
            if not self.settings.dry_run:
                self.repository.save_report(updated)
        ctx.reports = [
            r.model_copy(update={"decisions": [d for d in ctx.decisions if d.session_id == r.session_id]})
            for r in ctx.reports
        ]
        timings.append((STEP_LABELS[7], time.perf_counter() - t0))

        # Step 9 — code quality
        t0 = time.perf_counter()
        step(9, STEP_LABELS[8])
        if ctx.project_path:
            ctx.code_quality_label = code_quality_label(ctx.project_path)
        timings.append((STEP_LABELS[8], time.perf_counter() - t0))

        # Step 10 — episode scoring
        t0 = time.perf_counter()
        step(10, STEP_LABELS[9])
        decision_summaries = [d.summary for d in ctx.decisions if d.summary]
        ctx.episodes = []
        for stream in ctx.work_streams:
            episode = await score_episode(
                stream,
                ctx.reports,
                settings=self.settings,
                code_quality_label=ctx.code_quality_label,
                decision_summaries=decision_summaries,
            )
            ctx.episodes.append(episode)
        timings.append((STEP_LABELS[9], time.perf_counter() - t0))

        # Step 11 — assemble profile
        t0 = time.perf_counter()
        step(11, STEP_LABELS[10])
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
        timings.append((STEP_LABELS[10], time.perf_counter() - t0))

        return ctx.artifacts()

    @staticmethod
    def discover_cwd():
        return discover_repo_for_cwd()
