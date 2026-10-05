from open_paxel.models.domain import SessionFacts, UserMessage
from open_paxel.redact.transcript import read_full_transcript, redact_text

SECRETS = [
    "sk-proj-abc_def-ghijklmnopqrstuvwxyz0123",
    "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123",
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    "AKIAIOSFODNN7EXAMPLE",
    "xoxb-1234567890-abcdefghij",
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
]


def test_redacts_known_secret_formats():
    for secret in SECRETS:
        out = redact_text(f"use {secret} here", max_len=None)
        assert secret not in out, secret
        assert "[REDACTED]" in out


def test_redacts_json_style_keys():
    out = redact_text('{"api_key": "abc123", "password": "hunter2"}', max_len=None)
    assert "abc123" not in out
    assert "hunter2" not in out


def test_full_transcript_is_redacted(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("my key is sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123", encoding="utf-8")
    facts = SessionFacts(
        session_id="s",
        transcript_path=str(path),
        user_messages=[UserMessage(text="hi")],
        is_structured=False,
    )
    assert "sk-ant" not in read_full_transcript(facts)
