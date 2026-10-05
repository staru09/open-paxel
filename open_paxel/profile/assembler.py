from __future__ import annotations

from typing import TYPE_CHECKING

from open_paxel.config import Settings
from open_paxel.decisions.stats import aggregate_decisions
from open_paxel.models.domain import BuilderProfile, SessionReport
from open_paxel.profile.aggregate import build_profile
from open_paxel.profile.narrative_llm import generate_profile_narrative_llm

if TYPE_CHECKING:
    from open_paxel.pipeline.context import PipelineContext


async def assemble_profile(
    settings: Settings,
    repository,
    ctx: PipelineContext,
) -> BuilderProfile:
    artifacts = ctx.artifacts()
    if ctx.upload_id:
        repository.save_upload_artifacts(ctx.upload_id, artifacts)

    reports = repository.list_reports(limit=10_000)
    profile = build_profile(reports, repository.list_uploads())
    profile = profile.model_copy(update={"pipeline_artifacts": artifacts})

    llm_narrative = await generate_profile_narrative_llm(
        reports,
        settings,
        decision_stats=decision_stats_from_reports(reports),
        episodes=profile.episodes,
    )
    if llm_narrative:
        profile = profile.model_copy(update={"narrative": llm_narrative})

    repository.save_profile_cache(profile)
    return profile


def decision_stats_from_reports(reports: list[SessionReport]) -> dict[str, object]:
    all_decisions = []
    for report in reports:
        all_decisions.extend(report.decisions)
    return aggregate_decisions(all_decisions)
