from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from open_paxel.models.profile_narrative import ProfileNarrative
from open_paxel.models.pipeline_models import (
    Decision,
    Episode,
    PipelineArtifacts,
    SessionNarrative,
    SteeringTrace,
)
from open_paxel.models.scores import DimensionScore


DIMENSIONS = ("steering", "execution", "engineering", "product_instinct", "planning")


class UserMessage(BaseModel):
    text: str
    timestamp: datetime | None = None
    word_count: int = 0


class SessionFacts(BaseModel):
    session_id: str
    transcript_path: str
    project_path: str | None = None
    title: str | None = None
    git_branch: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int = 0
    models_used: list[str] = Field(default_factory=list)
    user_messages: list[UserMessage] = Field(default_factory=list)
    assistant_text_chars: int = 0
    tool_counts: dict[str, int] = Field(default_factory=dict)
    lines_added: int = 0
    lines_removed: int = 0
    files_edited: int = 0
    plan_mode_entries: int = 0
    plan_mode_exits: int = 0
    agent_runs: int = 0
    max_agent_duration_ms: int = 0
    tool_errors: int = 0
    redirect_hits: int = 0
    question_prompts: int = 0
    thank_you_count: int = 0
    caps_frustration_hits: int = 0
    test_lint_runs: int = 0
    raw_turn_count: int = 0
    total_tokens: int = 0
    source_format: str = "jsonl"
    is_structured: bool = True
    analyzable: bool = True
    filter_stats: dict[str, int] = Field(default_factory=dict)


class HeuristicMetrics(BaseModel):
    steering: float = 0.0
    execution: float = 0.0
    engineering: float = 0.0
    product_instinct: float = 0.0
    planning: float = 0.0
    redirect_rate: float = 0.0
    plan_mode_used: bool = False
    avg_prompt_words: float = 0.0
    short_prompt_ratio: float = 0.0
    top_phrases: list[tuple[str, int]] = Field(default_factory=list)
    primary_model: str | None = None
    model_distribution: dict[str, int] = Field(default_factory=dict)
    hour_histogram: dict[int, int] = Field(default_factory=dict)
    peak_hour: int | None = None
    productivity_label: str | None = None
    thank_you_count: int = 0
    agent_runs: int = 0
    max_agent_duration_ms: int = 0
    lines_added: int = 0
    redirect_hits: int = 0
    raw_turn_count: int = 0


class RedactedExcerpt(BaseModel):
    session_id: str
    first_prompt: str = ""
    steering_moments: list[str] = Field(default_factory=list)
    edit_summaries: list[str] = Field(default_factory=list)
    outcome_summary: str = ""
    window_excerpts: list[str] = Field(default_factory=list)
    raw_transcript: str = ""
    accumulated_summary: str = ""
    chunk_count: int = 0
    metrics_json: dict[str, Any] = Field(default_factory=dict)


class SessionScore(BaseModel):
    dimensions: dict[str, DimensionScore] = Field(default_factory=dict)
    archetype: str = "Explorer"
    signature_moves: list[str] = Field(default_factory=list)
    growth_edge: list[str] = Field(default_factory=list)
    insight_candidates: dict[str, str | None] = Field(default_factory=dict)


class SessionReport(BaseModel):
    session_id: str
    transcript_path: str
    project_path: str | None = None
    title: str | None = None
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    dimensions: dict[str, DimensionScore] = Field(default_factory=dict)
    archetype: str = "Explorer"
    signature_moves: list[str] = Field(default_factory=list)
    growth_edge: list[str] = Field(default_factory=list)
    insight_candidates: dict[str, str | None] = Field(default_factory=dict)
    heuristic_metrics: HeuristicMetrics | None = None
    upload_id: str | None = None
    session_narrative: SessionNarrative | None = None
    steering_traces: list[SteeringTrace] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    git_commit_ids: list[str] = Field(default_factory=list)
    analyzable: bool = True
    filter_stats: dict[str, int] = Field(default_factory=dict)
    code_quality_label: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class InsightCard(BaseModel):
    id: str
    title: str
    value: str
    subtitle: str | None = None
    question: str | None = None


class UploadReport(BaseModel):
    id: str
    created_at: datetime
    session_count: int
    project_paths: list[str] = Field(default_factory=list)
    session_ids: list[str] = Field(default_factory=list)
    pipeline_artifacts: PipelineArtifacts | None = None


class ProcessingJobFileResult(BaseModel):
    filename: str
    status: str
    session_id: str | None = None
    title: str | None = None
    error: str | None = None


class ProcessingJob(BaseModel):
    id: str
    status: str  # queued | processing | completed | failed
    created_at: datetime
    updated_at: datetime
    force: bool = False
    total_count: int = 0
    succeeded: int = 0
    failed: int = 0
    current_file: str | None = None
    current_step: str | None = None
    results: list[ProcessingJobFileResult] = Field(default_factory=list)
    upload_id: str | None = None
    logs: list[str] = Field(default_factory=list)
    openai_calls: list[dict] = Field(default_factory=list)


class BuilderProfile(BaseModel):
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    session_count: int = 0
    upload_count: int = 0
    dimensions: dict[str, float] = Field(default_factory=dict)
    dimension_trends: dict[str, list[float]] = Field(default_factory=dict)
    archetype: str = "Explorer"
    archetype_counts: dict[str, int] = Field(default_factory=dict)
    signature_moves: list[str] = Field(default_factory=list)
    growth_edge: list[str] = Field(default_factory=list)
    insight_cards: list[InsightCard] = Field(default_factory=list)
    narrative: ProfileNarrative | None = None
    episodes: list[Episode] = Field(default_factory=list)
    pipeline_artifacts: PipelineArtifacts | None = None
