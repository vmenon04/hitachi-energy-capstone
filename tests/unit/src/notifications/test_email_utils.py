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


def test_build_html_email_inlines_charts_after_matching_insight(monkeypatch):
    template_path = (
        Path(email_utils.__file__).resolve().parent
        / "templates"
        / "insights_email.html"
    )
    monkeypatch.setattr(email_utils, "_TEMPLATE_PATH", template_path)

    insights = "### Risk Alpha\n\nSome detail.\n\n---\n\n### Risk Beta\n\nOther detail."
    chart_images = {
        "Risk Alpha": [{"title": "Alpha chart", "image_b64": "abc", "sas_url": "https://example.com/alpha"}],
        "Risk Beta": [{"title": "Beta chart", "image_b64": "xyz", "sas_url": ""}],
    }

    html = email_utils.build_html_email(insights, chart_images=chart_images)

    alpha_chart_pos = html.index("Alpha chart")
    beta_chart_pos = html.index("Beta chart")
    risk_alpha_pos = html.index("Risk Alpha")
    risk_beta_pos = html.index("Risk Beta")

    # Each chart must appear after its own insight heading
    assert alpha_chart_pos > risk_alpha_pos
    assert beta_chart_pos > risk_beta_pos
    # Alpha's chart must appear before Beta's heading
    assert alpha_chart_pos < risk_beta_pos


def test_build_html_email_unmatched_charts_go_to_bottom(monkeypatch):
    template_path = (
        Path(email_utils.__file__).resolve().parent
        / "templates"
        / "insights_email.html"
    )
    monkeypatch.setattr(email_utils, "_TEMPLATE_PATH", template_path)

    insights = "### Known Insight\n\nSome detail."
    chart_images = {
        "Known Insight": [{"title": "Matched chart", "image_b64": "a", "sas_url": ""}],
        "Unrelated Title": [{"title": "Unmatched chart", "image_b64": "b", "sas_url": ""}],
    }

    html = email_utils.build_html_email(insights, chart_images=chart_images)

    matched_pos = html.index("Matched chart")
    unmatched_pos = html.index("Unmatched chart")

    # Unmatched chart falls through to after all insight sections
    assert unmatched_pos > matched_pos


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
        lambda insights_text, csv_name="data.csv", chart_images=None: f"<html>{csv_name}:{insights_text}</html>",
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


import base64
from types import SimpleNamespace


def test_build_attachments_returns_empty_for_none_and_empty_list():
    assert email_utils._build_attachments(None) == []
    assert email_utils._build_attachments([]) == []


def test_build_attachments_skips_missing_and_encodes_existing_file(tmp_path, capsys):
    existing = tmp_path / "report.txt"
    existing.write_text("hello world", encoding="utf-8")
    missing = tmp_path / "missing.pdf"

    attachments = email_utils._build_attachments([str(missing), str(existing)])

    captured = capsys.readouterr().out
    assert "[WARN] Attachment not found" in captured
    assert len(attachments) == 1
    assert attachments[0]["name"] == "report.txt"
    assert attachments[0]["contentType"] == "text/plain"
    assert attachments[0]["contentInBase64"] == base64.b64encode(b"hello world").decode("utf-8")


def test_build_attachments_uses_octet_stream_when_mime_unknown(tmp_path, monkeypatch):
    blob_file = tmp_path / "file.unknownext"
    blob_file.write_bytes(b"\x00\x01\x02")

    monkeypatch.setattr(email_utils.mimetypes, "guess_type", lambda *_args, **_kwargs: (None, None))

    attachments = email_utils._build_attachments([str(blob_file)])

    assert len(attachments) == 1
    assert attachments[0]["contentType"] == "application/octet-stream"


def test_build_html_email_uses_substring_fallback_for_chart_matching(monkeypatch):
    template_path = (
        Path(email_utils.__file__).resolve().parent
        / "templates"
        / "insights_email.html"
    )
    monkeypatch.setattr(email_utils, "_TEMPLATE_PATH", template_path)

    insights = "### Procurement Delay Risk\n\nDetails here."
    chart_images = {
        "Procurement Delay": [
            {"title": "Delay chart", "image_b64": "abc123", "sas_url": ""}
        ]
    }

    html = email_utils.build_html_email(insights, chart_images=chart_images)

    assert "Delay chart" in html
    assert html.index("Delay chart") > html.index("Procurement Delay Risk")


def test_build_html_email_handles_blank_title_and_no_matching_sections(monkeypatch):
    template_path = (
        Path(email_utils.__file__).resolve().parent
        / "templates"
        / "insights_email.html"
    )
    monkeypatch.setattr(email_utils, "_TEMPLATE_PATH", template_path)

    insights = "No markdown headings here."
    chart_images = {
        "Other Section": [
            {"title": "", "image_b64": "zzz", "sas_url": ""}
        ]
    }

    html = email_utils.build_html_email(insights, chart_images=chart_images)

    assert "data:image/png;base64,zzz" in html
    assert 'alt=""' in html


def test_send_insights_email_dry_run_logs_attachment_paths(monkeypatch, capsys):
    monkeypatch.setattr(email_utils, "build_html_email", lambda *_args, **_kwargs: "<html>preview</html>")

    class FailIfCalled:
        @staticmethod
        def from_connection_string(_conn_str):
            raise AssertionError("ACS client should not be initialized in dry-run mode")

    monkeypatch.setattr(email_utils, "EmailClient", FailIfCalled)

    email_utils.send_insights_email(
        insights_text="Insight body",
        csv_name="dataset.csv",
        connection_string="local",
        attachment_paths=["one.pdf", "two.html"],
    )

    captured = capsys.readouterr().out
    assert "[DRY-RUN] Attachments prepared: ['one.pdf', 'two.html']" in captured


def test_send_insights_email_uses_defaults_and_attaches_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        email_utils,
        "build_html_email",
        lambda insights_text, csv_name="data.csv", chart_images=None: "<html>body</html>",
    )

    attachment_file = tmp_path / "chart.html"
    attachment_file.write_text("<html>chart</html>", encoding="utf-8")

    sent = {}

    class FakePoller:
        def result(self):
            return {"id": "message-1"}

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
    monkeypatch.setattr(email_utils, "_ACS_CONNECTION_STRING", "Endpoint=default")
    monkeypatch.setattr(email_utils, "_EMAIL_SENDER", "defaultsender@example.com")
    monkeypatch.setattr(email_utils, "_EMAIL_RECIPIENT", "defaultrecipient@example.com")

    email_utils.send_insights_email(
        insights_text="Plain insight text",
        attachment_paths=[str(attachment_file)],
        chart_images={"A": [{"title": "Chart A", "image_b64": "img"}]},
    )

    message = sent["message"]
    assert sent["connection_string"] == "Endpoint=default"
    assert message["senderAddress"] == "defaultsender@example.com"
    assert message["recipients"]["to"][0]["address"] == "defaultrecipient@example.com"
    assert message["content"]["html"] == "<html>body</html>"
    assert message["content"]["subject"].startswith("Analysis")
    assert "Plain insight text" in message["content"]["plainText"]
    assert message["attachments"][0]["name"] == "chart.html"
    assert message["attachments"][0]["contentType"] == "text/html"


def test_send_insights_email_handles_result_object_with_message_id(monkeypatch, capsys):
    monkeypatch.setattr(
        email_utils,
        "build_html_email",
        lambda insights_text, csv_name="data.csv", chart_images=None: "<html>body</html>",
    )

    class FakeResult:
        message_id = "object-id-789"

    class FakePoller:
        def result(self):
            return FakeResult()

    class FakeClient:
        def begin_send(self, message):
            return FakePoller()

    class FakeEmailClient:
        @staticmethod
        def from_connection_string(conn_str):
            return FakeClient()

    monkeypatch.setattr(email_utils, "EmailClient", FakeEmailClient)

    email_utils.send_insights_email(
        insights_text="Insight text",
        connection_string="Endpoint=real",
    )

    captured = capsys.readouterr().out
    assert "Email delivered successfully. Message ID: object-id-789" in captured