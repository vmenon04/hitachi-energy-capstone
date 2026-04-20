"""
End-to-end test for the full pipeline (src/main.py).

All external services (Azure Blob Storage, Azure OpenAI, and Azure
Communication Services) are replaced with lightweight mocks so the
entire ``main()`` function can run deterministically in CI.

Strategy
--------
* Patch each imported function *at the point it is used* in ``src.main``
  (e.g. ``src.main.download_csv``) rather than deep inside its origin
  module, so the patches are independent of import-order subtleties.
* The conftest.py at tests/ sets the env vars that ``src.main`` and
  ``src.agents.agents`` read at module-import time, so this module can
  safely ``import src.main`` at collection time.
"""

import json
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

import src.main as pipeline


# ---------------------------------------------------------------------------
# Shared constants used across multiple tests
# ---------------------------------------------------------------------------

FAKE_INSIGHTS = """\
### Resource Allocation Risk

**Description:** Projects Alpha and Delta show signs of over-allocation.
**Evidence:** 4 open tasks assigned to Alice across 2 active projects.
**Impact:** Risk of delayed delivery.
**Recommended Action:** Redistribute tasks to reduce Alice's load.
"""

FAKE_CHART_PLAN = {
    "datasets": [
        {
            "dataset_name": "projects.csv",
            "insight_title": "Resource Allocation Risk",
            "charts": [
                {
                    "chart_type": "bar",
                    "x": "status",
                    "y": "status",
                    "aggregation": "count",
                    "title": "Project Status Distribution",
                }
            ],
        }
    ]
}

FAKE_DFS = {
    "projects.csv": pd.DataFrame(
        {
            "project_id": [1, 2, 3],
            "project_name": ["Alpha", "Beta", "Gamma"],
            "status": ["Active", "On Hold", "Completed"],
            "budget": [100_000, 200_000, 150_000],
        }
    )
}

FAKE_CHART_IMAGES = {
    "Resource Allocation Risk": [
        {
            "title": "Project Status Distribution",
            "image_b64": "abc123",
            "sas_url": "https://fake.blob.core.windows.net/bi-reports/charts/chart.html?sig=x",
        }
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_current_dfs():
    """Restore the module-level ``current_dfs`` dict after each test."""
    original = dict(pipeline.current_dfs)
    yield
    pipeline.current_dfs.clear()
    pipeline.current_dfs.update(original)


def _make_insights_result(text: str) -> dict:
    """Build a fake LangGraph-style agent result dict."""
    msg = MagicMock()
    msg.content = text
    return {"messages": [msg]}


# ---------------------------------------------------------------------------
# Helper: stack all the patches used in most tests
# ---------------------------------------------------------------------------

PATCH_DOWNLOAD = "src.main.download_csv"
PATCH_INSIGHTS = "src.main.generate_insights"
PATCH_CHART_PLAN = "src.main.generate_chart_plan"
PATCH_BUILD_CHARTS = "src.main.build_and_upload_chart_htmls"
PATCH_SEND_EMAIL = "src.main.send_insights_email"
PATCH_SHAREPOINT = "src.main.sharepoint_to_blob"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineHappyPath:
    def test_main_completes_without_exception(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=(["chart.html"], FAKE_CHART_IMAGES)),
            patch(PATCH_SEND_EMAIL) as mock_email,
        ):
            pipeline.main()

        assert mock_email.call_count == 4

    def test_download_csv_is_called(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS) as mock_dl,
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=([], {})),
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        mock_dl.assert_called_once()

    def test_generate_insights_receives_downloaded_dfs(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)) as mock_ins,
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=([], {})),
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        assert mock_ins.call_count == 4
        for c in mock_ins.call_args_list:
            assert c.args[0] is FAKE_DFS

    def test_generate_chart_plan_receives_insights_text(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN) as mock_cp,
            patch(PATCH_BUILD_CHARTS, return_value=([], {})),
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        assert mock_cp.call_count == 4
        for c in mock_cp.call_args_list:
            assert c.args[1] == FAKE_INSIGHTS

    def test_build_charts_receives_chart_plan(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=(["c.html"], FAKE_CHART_IMAGES)) as mock_bc,
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        assert mock_bc.call_count == 4
        for c in mock_bc.call_args_list:
            assert c.kwargs["chart_plan"] == FAKE_CHART_PLAN

    def test_send_email_receives_chart_images(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=(["c.html"], FAKE_CHART_IMAGES)),
            patch(PATCH_SEND_EMAIL) as mock_email,
        ):
            pipeline.main()

        assert mock_email.call_count == 4
        for c in mock_email.call_args_list:
            assert c.kwargs["chart_images"] == FAKE_CHART_IMAGES

    def test_each_persona_receives_distinct_system_prompt(self, monkeypatch):
        """main() passes a unique system_prompt to generate_insights for each persona."""
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)) as mock_ins,
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=([], {})),
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        assert mock_ins.call_count == 4
        system_prompts = [c.kwargs["system_prompt"] for c in mock_ins.call_args_list]
        assert len(set(system_prompts)) == 4, "Each persona must use a distinct system prompt"


class TestSharePointStep:
    def test_sharepoint_skipped_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_SHAREPOINT) as mock_sp,
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=([], {})),
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        mock_sp.assert_not_called()

    def test_sharepoint_called_when_env_is_set(self, monkeypatch):
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "fake-client-id")
        monkeypatch.setenv("SHAREPOINT_DRIVE_ID", "fake-drive-id")
        monkeypatch.setenv("SHAREPOINT_FOLDER_ID", "fake-folder-id")

        with (
            patch(PATCH_SHAREPOINT) as mock_sp,
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=([], {})),
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        mock_sp.assert_called_once_with("fake-drive-id", "fake-folder-id")

    def test_sharepoint_uses_default_folder_id_root(self, monkeypatch):
        monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "fake-client-id")
        monkeypatch.setenv("SHAREPOINT_DRIVE_ID", "fake-drive-id")
        monkeypatch.delenv("SHAREPOINT_FOLDER_ID", raising=False)

        with (
            patch(PATCH_SHAREPOINT) as mock_sp,
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result(FAKE_INSIGHTS)),
            patch(PATCH_CHART_PLAN, return_value=FAKE_CHART_PLAN),
            patch(PATCH_BUILD_CHARTS, return_value=([], {})),
            patch(PATCH_SEND_EMAIL),
        ):
            pipeline.main()

        # Default folder_id is "root" when the env var is absent
        mock_sp.assert_called_once_with("fake-drive-id", "root")


class TestPipelineEdgeCases:
    def test_no_email_sent_when_insights_empty(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=_make_insights_result("")),
            patch(PATCH_CHART_PLAN) as mock_cp,
            patch(PATCH_BUILD_CHARTS) as mock_bc,
            patch(PATCH_SEND_EMAIL) as mock_email,
        ):
            pipeline.main()

        mock_cp.assert_not_called()
        mock_bc.assert_not_called()
        mock_email.assert_not_called()

    def test_no_email_sent_when_insights_result_is_falsy(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, return_value=FAKE_DFS),
            patch(PATCH_INSIGHTS, return_value=None),
            patch(PATCH_CHART_PLAN) as mock_cp,
            patch(PATCH_BUILD_CHARTS) as mock_bc,
            patch(PATCH_SEND_EMAIL) as mock_email,
        ):
            pipeline.main()

        mock_cp.assert_not_called()
        mock_bc.assert_not_called()
        mock_email.assert_not_called()

    def test_exception_propagates_out_of_main(self, monkeypatch):
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)

        with (
            patch(PATCH_DOWNLOAD, side_effect=RuntimeError("blob storage unavailable")),
            patch(PATCH_SEND_EMAIL),
        ):
            with pytest.raises(RuntimeError, match="blob storage unavailable"):
                pipeline.main()

    def test_pipeline_step_ordering(self, monkeypatch):
        """Verify the six pipeline steps execute in the documented order."""
        monkeypatch.delenv("SHAREPOINT_CLIENT_ID", raising=False)
        call_order: list[str] = []

        def record(name):
            def _inner(*a, **kw):
                call_order.append(name)
                if name == "download_csv":
                    return FAKE_DFS
                if name == "generate_insights":
                    return _make_insights_result(FAKE_INSIGHTS)
                if name == "generate_chart_plan":
                    return FAKE_CHART_PLAN
                if name == "build_and_upload_chart_htmls":
                    return (["c.html"], FAKE_CHART_IMAGES)
                return None

            return _inner

        with (
            patch(PATCH_DOWNLOAD, side_effect=record("download_csv")),
            patch(PATCH_INSIGHTS, side_effect=record("generate_insights")),
            patch(PATCH_CHART_PLAN, side_effect=record("generate_chart_plan")),
            patch(PATCH_BUILD_CHARTS, side_effect=record("build_and_upload_chart_htmls")),
            patch(PATCH_SEND_EMAIL, side_effect=record("send_insights_email")),
        ):
            pipeline.main()

        assert call_order[0] == "download_csv"
        persona_steps = call_order[1:]
        expected_group = [
            "generate_insights",
            "generate_chart_plan",
            "build_and_upload_chart_htmls",
            "send_insights_email",
        ]
        assert len(persona_steps) == len(expected_group) * 4
        for i in range(4):
            assert persona_steps[i * 4 : (i + 1) * 4] == expected_group
