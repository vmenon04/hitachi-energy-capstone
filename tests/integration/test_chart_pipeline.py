"""
Integration tests: interactive HTML chart generation + real Azure Blob upload.

Uses real pandas DataFrames, real Plotly/Matplotlib rendering, and the real
Azure Storage SDK against a local Azurite emulator.  Tests are automatically
skipped when Azurite is not running.

Start Azurite locally with:
    docker run -p 10000:10000 mcr.microsoft.com/azure-storage/azurite azurite-blob
"""

import pytest
import pandas as pd
from azure.storage.blob import BlobServiceClient

from src.visualizations.html_report import build_and_upload_chart_htmls
from tests.integration.conftest import AZURITE_CONN_STR


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_df():
    return pd.DataFrame(
        {
            "project_id": [1, 2, 3, 4, 5],
            "project_name": ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
            "status": ["Active", "On Hold", "Completed", "Active", "Cancelled"],
            "budget": [100_000, 200_000, 150_000, 120_000, 50_000],
        }
    )


@pytest.fixture
def sample_dfs(project_df):
    return {"projects.csv": project_df}


@pytest.fixture
def bar_chart_plan():
    return {
        "datasets": [
            {
                "dataset_name": "projects.csv",
                "insight_title": "Project Status Overview",
                "charts": [
                    {
                        "chart_type": "bar",
                        "x": "status",
                        "y": "status",
                        "aggregation": "count",
                        "title": "Project Status Distribution",
                    },
                ],
            }
        ]
    }


@pytest.fixture
def two_chart_plan():
    return {
        "datasets": [
            {
                "dataset_name": "projects.csv",
                "insight_title": "Budget Analysis",
                "charts": [
                    {
                        "chart_type": "bar",
                        "x": "status",
                        "y": "budget",
                        "aggregation": "sum",
                        "title": "Budget by Status",
                    },
                    {
                        "chart_type": "bar",
                        "x": "status",
                        "y": "budget",
                        "aggregation": "mean",
                        "title": "Average Budget by Status",
                    },
                ],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildAndUploadChartHtmls:
    def test_returns_list_and_dict(self, sample_dfs, bar_chart_plan, azurite_container):
        container_name, conn_str = azurite_container
        html_paths, chart_images = build_and_upload_chart_htmls(
            sample_dfs, bar_chart_plan, conn_str, container_name
        )
        assert isinstance(html_paths, list)
        assert isinstance(chart_images, dict)

    def test_one_chart_produces_one_html_path(self, sample_dfs, bar_chart_plan, azurite_container):
        container_name, conn_str = azurite_container
        html_paths, _ = build_and_upload_chart_htmls(
            sample_dfs, bar_chart_plan, conn_str, container_name
        )
        assert len(html_paths) == 1

    def test_two_charts_produce_two_html_paths(self, sample_dfs, two_chart_plan, azurite_container):
        container_name, conn_str = azurite_container
        html_paths, _ = build_and_upload_chart_htmls(
            sample_dfs, two_chart_plan, conn_str, container_name
        )
        assert len(html_paths) == 2

    def test_blob_is_actually_uploaded_to_storage(self, sample_dfs, bar_chart_plan, azurite_container):
        """Verify the HTML chart was persisted in Azurite, not just locally."""
        container_name, conn_str = azurite_container
        build_and_upload_chart_htmls(sample_dfs, bar_chart_plan, conn_str, container_name)

        blobs = list(
            BlobServiceClient.from_connection_string(conn_str)
            .get_container_client(container_name)
            .list_blobs()
        )
        assert len(blobs) == 1
        assert blobs[0].name.endswith(".html")

    def test_two_charts_upload_two_blobs(self, sample_dfs, two_chart_plan, azurite_container):
        container_name, conn_str = azurite_container
        build_and_upload_chart_htmls(sample_dfs, two_chart_plan, conn_str, container_name)

        blobs = list(
            BlobServiceClient.from_connection_string(conn_str)
            .get_container_client(container_name)
            .list_blobs()
        )
        assert len(blobs) == 2

    def test_chart_images_keyed_by_insight_title(self, sample_dfs, bar_chart_plan, azurite_container):
        container_name, conn_str = azurite_container
        _, chart_images = build_and_upload_chart_htmls(
            sample_dfs, bar_chart_plan, conn_str, container_name
        )
        assert "Project Status Overview" in chart_images

    def test_chart_image_entry_has_required_fields(self, sample_dfs, bar_chart_plan, azurite_container):
        container_name, conn_str = azurite_container
        _, chart_images = build_and_upload_chart_htmls(
            sample_dfs, bar_chart_plan, conn_str, container_name
        )
        entry = chart_images["Project Status Overview"][0]
        assert "title" in entry
        assert "image_b64" in entry
        assert "sas_url" in entry

    def test_chart_image_b64_is_real_png(self, sample_dfs, bar_chart_plan, azurite_container):
        """image_b64 should decode to a valid PNG (starts with PNG magic bytes)."""
        import base64
        container_name, conn_str = azurite_container
        _, chart_images = build_and_upload_chart_htmls(
            sample_dfs, bar_chart_plan, conn_str, container_name
        )
        b64 = chart_images["Project Status Overview"][0]["image_b64"]
        raw = base64.b64decode(b64)
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

    def test_uploaded_blob_content_type_is_html(self, sample_dfs, bar_chart_plan, azurite_container):
        container_name, conn_str = azurite_container
        build_and_upload_chart_htmls(sample_dfs, bar_chart_plan, conn_str, container_name)

        cc = BlobServiceClient.from_connection_string(conn_str).get_container_client(container_name)
        blob_name = list(cc.list_blobs())[0].name
        props = cc.get_blob_client(blob_name).get_blob_properties()
        assert props.content_settings.content_type == "text/html"
