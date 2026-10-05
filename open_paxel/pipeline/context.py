from __future__ import annotations

from dataclasses import dataclass, field

from open_paxel.discover.scanner import RepoInfo
from open_paxel.models.domain import SessionReport
from open_paxel.models.pipeline_models import (
    Decision,
    Episode,
    GitCommit,
    PipelineArtifacts,
    WorkStream,
)


@dataclass
class PipelineContext:
    repo: RepoInfo | None = None
    project_path: str | None = None
    reports: list[SessionReport] = field(default_factory=list)
    git_commits: list[GitCommit] = field(default_factory=list)
    work_streams: list[WorkStream] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    code_quality_label: str | None = None
    upload_id: str | None = None

    def artifacts(self) -> PipelineArtifacts:
        return PipelineArtifacts(
            project_path=self.project_path,
            git_commits=self.git_commits,
            work_streams=self.work_streams,
            episodes=self.episodes,
            code_quality_label=self.code_quality_label,
            decisions=self.decisions,
        )

    def reports_by_id(self) -> dict[str, SessionReport]:
        return {r.session_id: r for r in self.reports}
