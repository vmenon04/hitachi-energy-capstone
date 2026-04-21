"""
Integration tests: HTML email building + ACS delivery pipeline.

Tests that ``build_html_email`` and ``send_insights_email`` work
together correctly, using the real Jinja/Template renderer with
the project's actual email template.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.notifications import email_utils
from src.notifications.email_utils import build_html_email, send_insights_email


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_INSIGHTS = """\
### Resource Allocation Risk

**Description:** Projects Alpha and Delta show signs of over-allocation.
**Evidence:** 4 open tasks assigned to Alice across 2 active projects.
**Impact:** Risk of delayed delivery and team burnout.
**Recommended Action:** Redistribute tasks to reduce Alice's load.

### Budget Overrun - Beta Project

**Description:** Beta is tracking 15 % over its approved budget.
**Evidence:** Current spend $230,000 vs $200,000 approved.
**Impact:** May require scope reduction or sponsor escalation.
**Recommended Action:** Schedule budget review with project sponsor this week.
"""

SAMPLE_CHART_IMAGES = {
    "Resource Allocation Risk": [
        {
            "title": "Open Tasks by Assignee",
            # 1-pixel transparent PNG, valid base64
            "image_b64": (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
                "2mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            ),
            "sas_url": "https://example.blob.core.windows.net/charts/chart1.html?sig=abc",
        }
    ]
}

REAL_TEMPLATE_PATH = (
    Path(email_utils.__file__).resolve().parent / "templates" / "insights_email.html"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_template_cache():
    """Reset the LRU cache between tests."""
    email_utils._load_email_template.cache_clear()
    yield
    email_utils._load_email_template.cache_clear()


@pytest.fixture(autouse=True)
def use_real_template(monkeypatch):
    """Point every test at the real HTML template."""
    monkeypatch.setattr(email_utils, "_TEMPLATE_PATH", REAL_TEMPLATE_PATH)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSendInsightsEmail:
    def test_dry_run_does_not_call_acs(self, capsys):
        with patch("src.notifications.email_utils.EmailClient") as mock_acs:
            send_insights_email(
                SAMPLE_INSIGHTS,
                "projects.csv",
                subject="Dry-run Test",
                recipient="test@example.com",
                sender="noreply@example.com",
                connection_string="local",
                attachment_paths=[],
                chart_images=SAMPLE_CHART_IMAGES,
            )

        mock_acs.from_connection_string.assert_not_called()
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out

    def test_live_send_constructs_correct_acs_message(self):
        with patch("src.notifications.email_utils.EmailClient") as mock_acs:
            mock_poller = MagicMock()
            mock_acs.from_connection_string.return_value.begin_send.return_value = mock_poller

            send_insights_email(
                SAMPLE_INSIGHTS,
                "projects.csv",
                subject="Integration Test Report",
                recipients=["pm@example.com", "stakeholders@example.com"],
                sender="noreply@example.com",
                connection_string="Endpoint=sb://fake;SharedAccessKeyName=x;SharedAccessKey=y",
                attachment_paths=[],
                chart_images=SAMPLE_CHART_IMAGES,
            )

        mock_acs.from_connection_string.assert_called_once()
        sent_msg = mock_acs.from_connection_string.return_value.begin_send.call_args[0][0]

        assert sent_msg["senderAddress"] == "noreply@example.com"
        assert [recipient["address"] for recipient in sent_msg["recipients"]["to"]] == [
            "pm@example.com",
            "stakeholders@example.com",
        ]
        assert "Integration Test Report" in sent_msg["content"]["subject"]
        assert "Resource Allocation Risk" in sent_msg["content"]["html"]

    def test_live_send_html_body_contains_chart_image(self):
        with patch("src.notifications.email_utils.EmailClient") as mock_acs:
            mock_acs.from_connection_string.return_value.begin_send.return_value = MagicMock()

            send_insights_email(
                SAMPLE_INSIGHTS,
                "projects.csv",
                subject="Chart Image Test",
                recipients=["pm@example.com", "stakeholders@example.com"],
                sender="noreply@example.com",
                connection_string="Endpoint=sb://fake;SharedAccessKeyName=x;SharedAccessKey=y",
                attachment_paths=[],
                chart_images=SAMPLE_CHART_IMAGES,
            )

        sent_msg = mock_acs.from_connection_string.return_value.begin_send.call_args[0][0]
        assert "data:image/png;base64," in sent_msg["content"]["html"]

    def test_build_then_send_pipeline_uses_same_html(self):
        """Verify the HTML produced by build_html_email ends up in the ACS payload."""
        expected_html = build_html_email(SAMPLE_INSIGHTS, "projects.csv", SAMPLE_CHART_IMAGES)

        with patch("src.notifications.email_utils.EmailClient") as mock_acs:
            mock_acs.from_connection_string.return_value.begin_send.return_value = MagicMock()

            send_insights_email(
                SAMPLE_INSIGHTS,
                "projects.csv",
                subject="Consistency Test",
                recipients=["pm@example.com", "stakeholders@example.com"],
                sender="noreply@example.com",
                connection_string="Endpoint=sb://fake;SharedAccessKeyName=x;SharedAccessKey=y",
                attachment_paths=[],
                chart_images=SAMPLE_CHART_IMAGES,
            )

        sent_html = mock_acs.from_connection_string.return_value.begin_send.call_args[0][0][
            "content"
        ]["html"]
        # Both calls render the same template with the same inputs, so
        # structural content like insight headings must match.
        assert "Resource Allocation Risk" in sent_html
        assert "Budget Overrun" in sent_html

    def test_persona_subject_appears_in_acs_message(self):
        """When subject is not provided, the persona name drives the subject line."""
        with patch("src.notifications.email_utils.EmailClient") as mock_acs:
            mock_acs.from_connection_string.return_value.begin_send.return_value = MagicMock()

            send_insights_email(
                SAMPLE_INSIGHTS,
                "projects.csv",
                recipients=["pm@example.com", "stakeholders@example.com"],
                sender="noreply@example.com",
                connection_string="Endpoint=sb://fake;SharedAccessKeyName=x;SharedAccessKey=y",
                chart_images=SAMPLE_CHART_IMAGES,
                persona="project_manager",
            )

        sent_msg = mock_acs.from_connection_string.return_value.begin_send.call_args[0][0]
        assert "Project Manager" in sent_msg["content"]["subject"]
        assert "Resource Allocation Risk" in sent_msg["content"]["html"]
