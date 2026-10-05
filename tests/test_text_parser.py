from pathlib import Path


from open_paxel.parser.auto import AutoTranscriptParser
from open_paxel.parser.text_session import TextSessionParser


FIXTURE_MD = Path(__file__).parent / "fixtures" / "sample_session.md"
FIXTURE_TXT = Path(__file__).parent / "fixtures" / "sample_session.txt"
FIXTURE_JSONL = Path(__file__).parent / "fixtures" / "sample.jsonl"


def test_parse_markdown_session():
    facts = TextSessionParser().parse(FIXTURE_MD)
    assert facts.session_id == "md-session-001"
    assert facts.title == "Refactor auth module"
    assert len(facts.user_messages) == 2
    assert facts.thank_you_count >= 1
    assert facts.test_lint_runs >= 1
    assert facts.tool_counts.get("Bash", 0) >= 1


def test_parse_txt_inline_labels():
    facts = TextSessionParser().parse(FIXTURE_TXT)
    assert facts.session_id.startswith("import-")
    assert facts.is_structured is True
    assert len(facts.user_messages) == 2
    assert facts.total_tokens > 0
    assert facts.redirect_hits >= 1
    assert facts.test_lint_runs >= 1


def test_parse_unstructured_prose(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text(
        "We need to refactor the auth module.\n\n"
        "The login flow is broken for OAuth users.\n\n"
        "```python\n"
        "def login():\n"
        "    pass\n"
        "```\n\n"
        "Run pytest before merging.\n\n"
        "Actually don't touch the database schema yet.\n",
        encoding="utf-8",
    )
    facts = TextSessionParser().parse(path)
    assert facts.is_structured is False
    assert facts.total_tokens > 20
    assert facts.test_lint_runs >= 1
    assert facts.redirect_hits >= 1
    assert facts.raw_turn_count >= 2


def test_auto_parser_routes_by_extension():
    auto = AutoTranscriptParser()
    jsonl_facts = auto.parse(FIXTURE_JSONL)
    md_facts = auto.parse(FIXTURE_MD)
    txt_facts = auto.parse(FIXTURE_TXT)
    assert jsonl_facts.session_id == "test-session-001"
    assert md_facts.session_id == "md-session-001"
    assert txt_facts.session_id.startswith("import-")
