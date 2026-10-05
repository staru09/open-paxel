from datetime import datetime

from open_paxel.metrics.heuristics import compute_heuristics
from open_paxel.models.domain import HeuristicMetrics, SessionFacts, SessionReport, UserMessage
from open_paxel.profile.insights import build_insight_cards, collect_profile_signals


def _report(**kwargs) -> SessionReport:
    defaults = {
        "session_id": "s1",
        "transcript_path": "/tmp/x.jsonl",
        "analyzed_at": datetime(2026, 6, 3, 23, 0),
        "dimensions": {},
        "archetype": "Architect",
    }
    defaults.update(kwargs)
    return SessionReport(**defaults)


def test_insight_cards_include_questions_and_narratives():
    facts = SessionFacts(
        session_id="s1",
        transcript_path="/tmp/x.jsonl",
        plan_mode_entries=1,
        thank_you_count=4,
        redirect_hits=8,
        raw_turn_count=10,
        lines_added=500,
        user_messages=[
            UserMessage(text="make it prettier please", word_count=4),
            UserMessage(text="thanks!", word_count=1),
        ],
    )
    metrics = compute_heuristics(facts)
    report = _report(heuristic_metrics=metrics, insight_candidates={"agent_relationship": "You treat the agent like a design partner."})

    cards = build_insight_cards(collect_profile_signals([report]))
    by_id = {c.id: c for c in cards}

    assert by_id["archetype"].question == "Which archetype are you?"
    assert by_id["archetype"].subtitle
    assert "plan" not in by_id
    assert by_id["thanks"].value == "You thank your agent"
    assert by_id["relationship"].question == "How do you see your agent?"


def test_phrase_card_aggregates_across_sessions():
    m1 = HeuristicMetrics(top_phrases=[("new three", 5)])
    m2 = HeuristicMetrics(top_phrases=[("new three", 3)])
    cards = build_insight_cards(
        collect_profile_signals([_report(heuristic_metrics=m1), _report(heuristic_metrics=m2)])
    )
    goto = next(c for c in cards if c.id == "goto")
    assert goto.value == "new three"
    assert "2 session" in goto.subtitle


def test_productivity_card_only_when_skewed():
    night_metrics = HeuristicMetrics(hour_histogram={23: 5, 0: 3, 14: 1})
    day_metrics = HeuristicMetrics(hour_histogram={14: 4, 15: 3})
    night_cards = build_insight_cards(collect_profile_signals([_report(heuristic_metrics=night_metrics)]))
    day_cards = build_insight_cards(collect_profile_signals([_report(heuristic_metrics=day_metrics)]))
    assert any(c.id == "productivity" for c in night_cards)
    assert not any(c.id == "productivity" for c in day_cards)
