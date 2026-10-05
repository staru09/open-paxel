from datetime import datetime

from open_paxel.metrics.heuristics import compute_heuristics
from open_paxel.models.domain import HeuristicMetrics, SessionFacts, SessionReport, UserMessage
from open_paxel.profile.aggregate import build_profile
from open_paxel.profile.narrative_heuristic import build_profile_narrative
from open_paxel.profile.insights import collect_profile_signals


def _report(**kwargs) -> SessionReport:
    defaults = {
        "session_id": "s1",
        "transcript_path": "/tmp/x.jsonl",
        "analyzed_at": datetime(2026, 6, 3, 23, 0),
        "dimensions": {},
        "archetype": "Architect",
        "signature_moves": ["Model the data owner before accepting AI structure"],
        "growth_edge": ["Write a short plan before long runs"],
    }
    defaults.update(kwargs)
    return SessionReport(**defaults)


def test_build_profile_includes_narrative_sections():
    facts = SessionFacts(
        session_id="s1",
        transcript_path="/tmp/x.jsonl",
        project_path="/projects/gpu-viz",
        title="GPU visualizer deployment",
        plan_mode_entries=0,
        redirect_hits=5,
        raw_turn_count=10,
        user_messages=[UserMessage(text="fix the cache block", word_count=4)],
    )
    metrics = compute_heuristics(facts)
    report = _report(
        project_path="/projects/gpu-viz",
        title="GPU visualizer deployment",
        heuristic_metrics=metrics,
    )
    profile = build_profile([report], [])

    assert profile.narrative is not None
    assert profile.narrative.narrative
    assert profile.narrative.what_you_built
    assert profile.narrative.decision_patterns
    assert profile.narrative.strengths
    assert profile.narrative.growth_areas


def test_narrative_heuristic_matched_pattern():
    narrative = build_profile_narrative(
        [_report()],
        collect_profile_signals([_report()]),
        archetype="Architect",
        signature_moves=["Model the data owner"],
        growth_edge=["Plan before coding"],
    )
    assert narrative.matched_pattern == "Model the data owner"
    assert narrative.matched_pattern_category


def test_profile_keeps_episodes_from_all_uploads():
    from open_paxel.models.domain import UploadReport
    from open_paxel.models.pipeline_models import Episode, PipelineArtifacts
    from open_paxel.models.scores import DimensionScore

    def upload(uid, day, episodes):
        return UploadReport(
            id=uid,
            created_at=datetime(2026, 6, day),
            session_count=1,
            pipeline_artifacts=PipelineArtifacts(episodes=episodes),
        )

    def episode(eid, sessions, score):
        dims = {"planning": DimensionScore(score=score)}
        return Episode(id=eid, work_stream_id=eid, session_ids=sessions, dimensions=dims)

    uploads = [
        upload("old", 1, [episode("a", ["s1"], 10), episode("b", ["s2"], 50)]),
        # Re-analyzed s1 in a newer upload: replaces episode "a", "b" stays.
        upload("new", 2, [episode("a2", ["s1"], 90)]),
    ]
    profile = build_profile([_report()], uploads)

    assert sorted(e.id for e in profile.episodes) == ["a2", "b"]
    assert profile.dimensions["planning"] == 70.0


def test_rename_keeps_cached_llm_narrative(tmp_path):
    from open_paxel.db.repository import SQLiteRepository
    from open_paxel.models.profile_narrative import ProfileNarrative

    repo = SQLiteRepository(tmp_path / "profile.db")
    repo.save_report(_report())
    llm = ProfileNarrative(narrative="from the LLM")
    repo.save_profile_cache(repo.get_profile().model_copy(update={"narrative": llm}))

    repo.update_report_title("s1", "Renamed")

    assert repo.get_profile().narrative.narrative == "from the LLM"
