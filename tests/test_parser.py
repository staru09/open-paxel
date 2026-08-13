from pathlib import Path

import pytest

from open_paxel.metrics.heuristics import compute_heuristics
from open_paxel.parser.claude_jsonl import ClaudeCodeJsonlParser, decode_project_path


FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def test_decode_project_path():
    assert "Z:" in decode_project_path("Z--June-26-brain-dump")
    assert decode_project_path("c--Users-91745-OneDrive-Desktop-staru09-github-io") == (
        r"C:\Users\91745\OneDrive\Desktop\staru09\github\io"
    )
    assert decode_project_path("d--Projects-MyRepo") == r"D:\Projects\MyRepo"
    assert decode_project_path("E--Code-open-paxel") == r"E:\Code\open\paxel"



def test_parse_sample_jsonl():
    facts = ClaudeCodeJsonlParser().parse(FIXTURE)
    assert facts.session_id == "test-session-001"
    assert facts.title == "Fix login bug"
    assert len(facts.user_messages) >= 2
    assert facts.tool_counts.get("Write", 0) >= 1
    assert facts.thank_you_count >= 1
    assert facts.test_lint_runs >= 1


def test_heuristics_from_sample():
    facts = ClaudeCodeJsonlParser().parse(FIXTURE)
    metrics = compute_heuristics(facts)
    assert 0 <= metrics.steering <= 100
    assert 0 <= metrics.execution <= 100
    assert metrics.plan_mode_used is False


def test_parse_heterogeneous_transcript_fields():
    path = Path(__file__).parent / "fixtures" / "string_tool_result.jsonl"
    facts = ClaudeCodeJsonlParser().parse(path)
    assert facts.session_id == "edge-case-session"
    assert len(facts.user_messages) == 1
    assert facts.lines_added == 10
    assert facts.lines_removed == 2
    assert facts.max_agent_duration_ms == 5000
    assert facts.agent_runs == 1
