from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pandas as pd
import pytest


class FakeBlobClient:
    def __init__(self, blob_name: str):
        self.blob_name = blob_name
        self.uploads = []

    def upload_blob(self, data, overwrite=False, content_settings=None):
        payload = data.read() if hasattr(data, "read") else data
        self.uploads.append(
            {
                "payload": payload,
                "overwrite": overwrite,
                "content_type": getattr(content_settings, "content_type", None),
            }
        )


class FakeContainerClient:
    def __init__(self):
        self.clients = {}

    def get_blob_client(self, blob_name: str):
        client = self.clients.get(blob_name)
        if client is None:
            client = FakeBlobClient(blob_name)
            self.clients[blob_name] = client
        return client


class FakeCredential:
    account_key = "fake-account-key"


class FakeBlobServiceClient:
    def __init__(self):
        self.account_name = "fakeacct"
        self.credential = FakeCredential()
        self.container = FakeContainerClient()

    @classmethod
    def from_connection_string(cls, connection_string: str):
        instance = cls()
        instance.connection_string = connection_string
        return instance

    def get_container_client(self, container_name: str):
        self.requested_container = container_name
        return self.container


class FakeBlobSasPermissions:
    def __init__(self, read=False):
        self.read = read


class FakeContentSettings:
    def __init__(self, content_type=None):
        self.content_type = content_type


@pytest.fixture
def html_report_module(monkeypatch):
    fake_azure = types.ModuleType("azure")
    fake_storage = types.ModuleType("azure.storage")
    fake_blob = types.ModuleType("azure.storage.blob")

    fake_blob.BlobServiceClient = FakeBlobServiceClient
    fake_blob.BlobSasPermissions = FakeBlobSasPermissions
    fake_blob.ContentSettings = FakeContentSettings
    fake_blob.generate_blob_sas = lambda **kwargs: "fake-sas-token"

    monkeypatch.setitem(sys.modules, "azure", fake_azure)
    monkeypatch.setitem(sys.modules, "azure.storage", fake_storage)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", fake_blob)

    sys.modules.pop("src.visualizations.html_report", None)
    module = importlib.import_module("src.visualizations.html_report")
    return module


class TestHelpers:
    def test_safe_name_replaces_problem_characters(self, html_report_module):
        assert html_report_module._safe_name("folder\\my file.csv") == "folder_my_file"

    def test_normalize_datetime_coerces_invalid_values(self, html_report_module):
        series = pd.Series(["2026-01-01", "not-a-date"])
        result = html_report_module._normalize_datetime(series)

        assert str(result.iloc[0]).startswith("2026-01-01")
        assert pd.isna(result.iloc[1])

    def test_validate_column_true_and_false_cases(self, html_report_module):
        df = pd.DataFrame({"a": [1], "b": [2]})

        assert html_report_module._validate_column(df, "a") is True
        assert html_report_module._validate_column(df, None) is False
        assert html_report_module._validate_column(df, "missing") is False


class TestAggregateForChart:
    def test_returns_none_for_missing_x(self, html_report_module):
        df = pd.DataFrame({"category": ["A"]})
        assert html_report_module._aggregate_for_chart(df, "missing", None, "count", "bar") is None

    def test_line_count_normalizes_dates_drops_invalid_and_sorts(self, html_report_module):
        df = pd.DataFrame({"created_at": ["bad", "2026-01-03", "2026-01-01", "2026-01-01"]})

        result = html_report_module._aggregate_for_chart(df, "created_at", None, "count", "line")

        assert result is not None
        assert list(result["value"]) == [2, 1]
        assert list(result["created_at"].dt.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-03"]

    def test_line_count_returns_none_when_all_dates_invalid(self, html_report_module):
        df = pd.DataFrame({"created_at": ["bad", None]})
        assert html_report_module._aggregate_for_chart(df, "created_at", None, "count", "line") is None

    def test_sum_returns_grouped_values(self, html_report_module):
        df = pd.DataFrame({"team": ["B", "A", "A"], "hours": [3, 1, 2]})

        result = html_report_module._aggregate_for_chart(df, "team", "hours", "sum", "bar")

        assert list(result["team"]) == ["A", "B"]
        assert list(result["value"]) == [3, 3]

    def test_mean_returns_grouped_values(self, html_report_module):
        df = pd.DataFrame({"team": ["A", "A", "B"], "hours": [2, 4, 10]})

        result = html_report_module._aggregate_for_chart(df, "team", "hours", "mean", "bar")

        assert list(result["team"]) == ["A", "B"]
        assert list(result["value"]) == [3.0, 10.0]

    def test_returns_none_for_missing_or_invalid_y(self, html_report_module):
        df = pd.DataFrame({"team": ["A"], "hours": [1]})

        assert html_report_module._aggregate_for_chart(df, "team", None, "sum", "bar") is None
        assert html_report_module._aggregate_for_chart(df, "team", "missing", "sum", "bar") is None

    def test_returns_none_for_id_columns_and_unknown_aggregation(self, html_report_module):
        df = pd.DataFrame({"team": ["A"], "employee_id": [1], "hours": [5]})

        assert html_report_module._aggregate_for_chart(df, "team", "employee_id", "sum", "bar") is None
        assert html_report_module._aggregate_for_chart(df, "team", "hours", "median", "bar") is None


class TestRenderChartHtml:
    def test_rejects_invalid_spec_inputs(self, html_report_module, tmp_path):
        df = pd.DataFrame({"x": [1], "y": [2]})

        assert html_report_module._render_chart_html(
            df,
            "demo.csv",
            {"chart_type": "pie", "x": "x", "aggregation": "count"},
            tmp_path,
            0,
        ) is None
        assert html_report_module._render_chart_html(
            df,
            "demo.csv",
            {"chart_type": "bar", "x": "x", "aggregation": "median"},
            tmp_path,
            0,
        ) is None
        assert html_report_module._render_chart_html(
            df,
            "demo.csv",
            {"chart_type": "bar", "x": 123, "aggregation": "count"},
            tmp_path,
            0,
        ) is None

    def test_returns_none_when_grouping_fails(self, html_report_module, tmp_path, monkeypatch):
        df = pd.DataFrame({"x": [1], "y": [2]})
        monkeypatch.setattr(html_report_module, "_aggregate_for_chart", lambda **kwargs: None)

        result = html_report_module._render_chart_html(
            df,
            "demo.csv",
            {"chart_type": "bar", "x": "x", "aggregation": "count", "title": "Demo"},
            tmp_path,
            0,
        )

        assert result is None

    def test_renders_bar_chart_and_writes_html(self, html_report_module, tmp_path):
        df = pd.DataFrame({"team": [f"T{i}" for i in range(7)], "hours": list(range(1, 8))})

        result = html_report_module._render_chart_html(
            df,
            "my file.csv",
            {"chart_type": "bar", "x": "team", "y": "hours", "aggregation": "sum", "title": "Hours by Team"},
            tmp_path,
            7,
        )

        assert result is not None
        assert result["dataset"] == "my file.csv"
        assert result["title"] == "Hours by Team"
        assert result["blob_name"] == "my_file_7_bar.html"
        assert Path(result["local_path"]).exists()
        assert len(result["image_b64"]) > 50

    def test_renders_line_chart_with_default_title(self, html_report_module, tmp_path):
        df = pd.DataFrame({"created_at": ["2026-01-01", "2026-01-02", "2026-01-02"]})

        result = html_report_module._render_chart_html(
            df,
            "timeline.csv",
            {"chart_type": "line", "x": "created_at", "aggregation": "count"},
            tmp_path,
            1,
        )

        assert result is not None
        assert result["title"] == "timeline.csv chart"
        assert result["blob_name"] == "timeline_1_line.html"


class TestBuildAndUploadChartHtmls:
    def test_builds_uploads_and_groups_chart_output(self, html_report_module, monkeypatch, tmp_path):
        monkeypatch.setattr(html_report_module.tempfile, "mkdtemp", lambda prefix: str(tmp_path))
        service = FakeBlobServiceClient()
        monkeypatch.setattr(
            html_report_module.BlobServiceClient,
            "from_connection_string",
            classmethod(lambda cls, connection_string: service),
        )

        dfs = {
            "tasks.csv": pd.DataFrame(
                {
                    "status": ["Open", "Open", "Closed"],
                    "hours": [5, 3, 2],
                    "created_at": ["2026-01-02", "2026-01-01", "2026-01-02"],
                }
            )
        }
        chart_plan = {
            "datasets": [
                {
                    "dataset_name": "tasks.csv",
                    "insight_title": "Workload summary",
                    "charts": [
                        {"chart_type": "bar", "x": "status", "y": "hours", "aggregation": "sum", "title": "Hours by Status"},
                        {"chart_type": "line", "x": "created_at", "aggregation": "count", "title": "Tasks Over Time"},
                    ],
                }
            ]
        }

        local_paths, chart_images = html_report_module.build_and_upload_chart_htmls(
            dfs=dfs,
            chart_plan=chart_plan,
            connection_string="UseDevelopmentStorage=true",
            container_name="bi-reports",
            blob_prefix="charts/",
        )

        assert len(local_paths) == 2
        assert set(chart_images.keys()) == {"Workload summary"}
        assert [item["title"] for item in chart_images["Workload summary"]] == ["Hours by Status", "Tasks Over Time"]
        assert all(
            item["sas_url"].startswith("https://fakeacct.blob.core.windows.net/bi-reports/charts/")
            for item in chart_images["Workload summary"]
        )
        assert all(item["sas_url"].endswith("fake-sas-token") for item in chart_images["Workload summary"])

        assert set(service.container.clients.keys()) == {
            "charts/tasks_0_bar.html",
            "charts/tasks_1_line.html",
        }
        for blob_client in service.container.clients.values():
            assert blob_client.uploads[0]["overwrite"] is True
            assert blob_client.uploads[0]["content_type"] == "text/html"
            assert blob_client.uploads[0]["payload"]

    def test_skips_missing_datasets_invalid_specs_and_render_exceptions(
        self,
        html_report_module,
        monkeypatch,
        tmp_path,
        capsys,
    ):
        monkeypatch.setattr(html_report_module.tempfile, "mkdtemp", lambda prefix: str(tmp_path))
        service = FakeBlobServiceClient()
        monkeypatch.setattr(
            html_report_module.BlobServiceClient,
            "from_connection_string",
            classmethod(lambda cls, connection_string: service),
        )

        real_render = html_report_module._render_chart_html

        def wrapped_render(**kwargs):
            spec = kwargs["spec"]
            if spec.get("title") == "Boom":
                raise RuntimeError("explode")
            return real_render(**kwargs)

        monkeypatch.setattr(html_report_module, "_render_chart_html", wrapped_render)

        dfs = {"valid.csv": pd.DataFrame({"group": ["A", "B"], "value": [1, 2]})}
        chart_plan = {
            "datasets": [
                {"dataset_name": "missing.csv", "charts": [{"chart_type": "bar", "x": "group", "aggregation": "count"}]},
                {
                    "dataset_name": "valid.csv",
                    "charts": [
                        {"chart_type": "pie", "x": "group", "aggregation": "count", "title": "Invalid"},
                        {"chart_type": "bar", "x": "group", "aggregation": "count", "title": "Good"},
                        {"chart_type": "bar", "x": "group", "aggregation": "count", "title": "Boom"},
                    ],
                },
            ]
        }

        local_paths, chart_images = html_report_module.build_and_upload_chart_htmls(
            dfs=dfs,
            chart_plan=chart_plan,
            connection_string="UseDevelopmentStorage=true",
            container_name="bi-reports",
        )

        captured = capsys.readouterr().out
        assert "Dataset from chart plan not found: missing.csv" in captured
        assert "Skipped invalid/unrenderable chart spec" in captured
        assert "Failed to render chart for valid.csv: explode" in captured
        assert "Total HTML charts generated and uploaded: 1" in captured
        assert len(local_paths) == 1
        assert set(chart_images.keys()) == {"valid.csv"}
        assert chart_images["valid.csv"][0]["title"] == "Good"