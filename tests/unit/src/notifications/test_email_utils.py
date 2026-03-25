from pathlib import Path

import pytest

from src.notifications import email_utils


@pytest.fixture(autouse=True)
def clear_template_cache():
    """Ensure each test sees a fresh template cache."""
    email_utils._load_email_template.cache_clear()
    yield
    email_utils._load_email_template.cache_clear()


def test_build_html_email_renders_template_content(monkeypatch):
    template_path = (
        Path(email_utils.__file__).resolve().parent
        / "templates"
        / "insights_email.html"
    )
    monkeypatch.setattr(email_utils, "_TEMPLATE_PATH", template_path)

    html = email_utils.build_html_email(
        "1. Revenue grew in APAC\n2. Churn risk increased in SMB",
        csv_name="sales_snapshot.csv",
    )

    assert "${insights_html}" not in html


def test_load_email_template_raises_if_file_missing(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing_template.html"
    monkeypatch.setattr(email_utils, "_TEMPLATE_PATH", missing_path)

    with pytest.raises(FileNotFoundError, match="Email template not found"):
        email_utils._load_email_template()


def test_send_insights_email_dry_run_does_not_call_acs(monkeypatch, capsys):
    monkeypatch.setattr(email_utils, "build_html_email", lambda *_args, **_kwargs: "<html>ok</html>")

    class FailIfCalled:
        @staticmethod
        def from_connection_string(_conn_str):
            raise AssertionError("ACS client should not be initialized in dry-run mode")

    monkeypatch.setattr(email_utils, "EmailClient", FailIfCalled)

    email_utils.send_insights_email(
        insights_text="- Insight A",
        csv_name="dataset.csv",
        connection_string="local",
    )

    captured = capsys.readouterr().out
    assert "[DRY-RUN] Email not sent." in captured


def test_send_insights_email_builds_expected_acs_message(monkeypatch):
    monkeypatch.setattr(
        email_utils,
        "build_html_email",
        lambda insights_text, csv_name="data.csv": f"<html>{csv_name}:{insights_text}</html>",
    )

    sent = {}

    class FakePoller:
        def result(self):
            return {"id": "abc-123"}

    class FakeClient:
        def begin_send(self, message):
            sent["message"] = message
            return FakePoller()

    class FakeEmailClient:
        @staticmethod
        def from_connection_string(conn_str):
            sent["connection_string"] = conn_str
            return FakeClient()

    monkeypatch.setattr(email_utils, "EmailClient", FakeEmailClient)

    email_utils.send_insights_email(
        insights_text="Top risk is delayed procurement.",
        csv_name="issues.csv",
        subject="Daily Insights",
        recipient="ops@example.com",
        sender="noreply@example.com",
        connection_string="Endpoint=example",
    )

    message = sent["message"]
    assert sent["connection_string"] == "Endpoint=example"
    assert message["senderAddress"] == "noreply@example.com"
    assert message["recipients"]["to"][0]["address"] == "ops@example.com"
    assert message["content"]["subject"] == "Daily Insights"
    assert "issues.csv" in message["content"]["html"]
    assert "Top risk is delayed procurement." in message["content"]["plainText"]
