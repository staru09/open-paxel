from __future__ import annotations

import logging
from pathlib import Path

from open_paxel.metrics.heuristics import blend_dimension, compute_heuristics
from open_paxel.models.domain import DIMENSIONS, DimensionScore, SessionReport, utcnow
from open_paxel.parser.auto import AutoTranscriptParser
from open_paxel.redact.excerpts import build_excerpts
from open_paxel.redact.transcript import read_full_transcript
from open_paxel.scorer.registry import get_scorer
from open_paxel.scorer.session_narrative import generate_session_narrative
from open_paxel.scorer.transcript_condenser import condense_transcript, needs_condensing
from open_paxel.pipeline.steps.steering_traces import attach_steering_traces
from open_paxel.config import Settings

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(self, settings: Settings, repository, parser=None, scorer=None):
        self.settings = settings
        self.repository = repository
        self.parser = parser or AutoTranscriptParser()
        self._scorer = scorer

    def _get_scorer(self):
        if self._scorer is None:
            self._scorer = get_scorer(self.settings)
        return self._scorer

    async def analyze_file(
        self,
        path: Path,
        upload_id: str | None = None,
        force: bool = False,
    ) -> SessionReport:
        path = Path(path)
        logger.info("Parsing %s", path.name)
        facts = self.parser.parse(path)

        if (
            not force
            and self.repository.report_exists(facts.session_id)
            and not self.settings.dry_run
        ):
            existing = self.repository.get_report(facts.session_id)
            if existing:
                logger.info("Cache hit for session %s", facts.session_id)
                return existing

        if not facts.analyzable:
            logger.info("Session %s not analyzable: %s", facts.session_id, facts.filter_stats)

        metrics = compute_heuristics(facts)
        excerpts = build_excerpts(facts, metrics)

        session_narrative = None
        llm_score = None
        if facts.analyzable:
            # Oversized transcripts overflow local-model context windows. Condense
            # the full session into a running summary so scoring sees the whole
            # session instead of a truncated head (or a failed/empty LLM call).
            full_text = read_full_transcript(facts)
            if needs_condensing(full_text, self.settings):
                summary, chunk_count = await condense_transcript(full_text, self.settings)
                if summary:
                    excerpts = excerpts.model_copy(
                        update={
                            "raw_transcript": summary,
                            "accumulated_summary": summary,
                            "chunk_count": chunk_count,
                            "metrics_json": {**excerpts.metrics_json, "condensed": True},
                        }
                    )
            session_narrative = await generate_session_narrative(
                facts, metrics, excerpts, self.settings
            )
            if self._scorer is not None or self.settings.legacy_scorer:
                scorer = self._scorer or self._get_scorer()
                llm_score = await scorer.score_session(facts, metrics, excerpts)

        dimensions: dict[str, DimensionScore] = {}
        archetype = "Explorer"
        signature_moves: list[str] = []
        growth_edge: list[str] = []
        insight_candidates: dict[str, str | None] = {}

        if llm_score:
            archetype = llm_score.archetype
            signature_moves = llm_score.signature_moves
            growth_edge = llm_score.growth_edge
            insight_candidates = llm_score.insight_candidates
            for dim in DIMENSIONS:
                h = getattr(metrics, dim)
                llm_dim = llm_score.dimensions.get(dim)
                llm_val = llm_dim.score if llm_dim else h
                weight = 0.5 if dim in ("engineering", "product_instinct") else 0.4
                blended = blend_dimension(h, llm_val, heuristic_weight=weight)
                dimensions[dim] = DimensionScore(
                    score=blended,
                    narrative=llm_dim.narrative if llm_dim else "",
                    evidence=llm_dim.evidence if llm_dim else [],
                )
        else:
            for dim in DIMENSIONS:
                h = getattr(metrics, dim)
                dimensions[dim] = DimensionScore(
                    score=h,
                    narrative="Heuristic score; episode rollup may refine.",
                    evidence=[],
                )

        report = SessionReport(
            session_id=facts.session_id,
            transcript_path=str(path),
            project_path=facts.project_path,
            title=facts.title,
            analyzed_at=utcnow(),
            started_at=facts.started_at,
            ended_at=facts.ended_at,
            dimensions=dimensions,
            archetype=archetype,
            signature_moves=signature_moves,
            growth_edge=growth_edge,
            insight_candidates=insight_candidates,
            heuristic_metrics=metrics,
            upload_id=upload_id,
            session_narrative=session_narrative,
            analyzable=facts.analyzable,
            filter_stats=facts.filter_stats,
        )
        report = attach_steering_traces(report, facts)

        if not self.settings.dry_run:
            self.repository.save_report(report)
        logger.info("Saved report %s (%s)", report.session_id, report.title or "Untitled")
        return report
