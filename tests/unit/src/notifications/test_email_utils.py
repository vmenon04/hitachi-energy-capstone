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
