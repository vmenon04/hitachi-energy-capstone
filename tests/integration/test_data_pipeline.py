"""
Integration tests: CSV download → DataFrame metadata pipeline.

Tests that ``download_csv`` and ``build_dataset_metadata`` work together
using the real Azure Storage SDK against a local Azurite emulator.
Tests are automatically skipped when Azurite is not running.

Start Azurite locally with:
    docker run -p 10000:10000 mcr.microsoft.com/azure-storage/azurite azurite-blob
"""

import pytest
from azure.storage.blob import BlobServiceClient

from src.utils.data_utils import download_csv, build_dataset_metadata
from tests.integration.conftest import AZURITE_CONN_STR


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

PROJECTS_CSV = (
    "project_id,project_name,status,budget\n"
    "1,Alpha,Active,100000\n"
    "2,Beta,On Hold,200000\n"
    "3,Gamma,Completed,150000\n"
)

TASKS_CSV = (
    "task_id,project_id,assignee,due_date,completed\n"
    "101,1,Alice,2026-03-01,True\n"
    "102,1,Bob,2026-03-15,False\n"
    "103,2,Carol,2026-04-01,False\n"
)

README_TXT = "This is not a CSV file."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_container(azurite_container):
    """
    Uploads projects.csv, tasks.csv, and README.txt into a fresh Azurite
    container and yields ``(container_name, conn_str)``.
    """
    container_name, conn_str = azurite_container
    cc = BlobServiceClient.from_connection_string(conn_str).get_container_client(container_name)
    cc.upload_blob("projects.csv", PROJECTS_CSV.encode())
    cc.upload_blob("tasks.csv", TASKS_CSV.encode())
    cc.upload_blob("README.txt", README_TXT.encode())
    return container_name, conn_str


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDownloadCsvAndMetadata:
    def test_only_csv_blobs_are_loaded(self, populated_container):
        container_name, conn_str = populated_container
        dfs = download_csv(conn_str, container_name)
        assert set(dfs.keys()) == {"projects.csv", "tasks.csv"}

    def test_non_csv_blob_is_excluded(self, populated_container):
        container_name, conn_str = populated_container
        dfs = download_csv(conn_str, container_name)
        assert "README.txt" not in dfs

    def test_dataframe_row_counts_match_csv(self, populated_container):
        container_name, conn_str = populated_container
        dfs = download_csv(conn_str, container_name)
        assert len(dfs["projects.csv"]) == 3
        assert len(dfs["tasks.csv"]) == 3

    def test_dataframe_columns_match_csv_headers(self, populated_container):
        container_name, conn_str = populated_container
        dfs = download_csv(conn_str, container_name)
        assert list(dfs["projects.csv"].columns) == ["project_id", "project_name", "status", "budget"]
        assert list(dfs["tasks.csv"].columns) == ["task_id", "project_id", "assignee", "due_date", "completed"]

    def test_metadata_contains_all_dataset_names(self, populated_container):
        container_name, conn_str = populated_container
        dfs = download_csv(conn_str, container_name)
        metadata = build_dataset_metadata(dfs)
        assert "projects.csv" in metadata
        assert "tasks.csv" in metadata

    def test_metadata_contains_column_names(self, populated_container):
        container_name, conn_str = populated_container
        dfs = download_csv(conn_str, container_name)
        metadata = build_dataset_metadata(dfs)
        assert "project_name" in metadata
        assert "assignee" in metadata

    def test_metadata_includes_row_count(self, populated_container):
        container_name, conn_str = populated_container
        dfs = download_csv(conn_str, container_name)
        metadata = build_dataset_metadata(dfs)
        # Both CSVs have 3 rows; the count should appear in the metadata string.
        assert "3" in metadata

    def test_empty_container_returns_empty_dfs(self, azurite_container):
        container_name, conn_str = azurite_container
        dfs = download_csv(conn_str, container_name)
        assert dfs == {}

    def test_empty_container_metadata_does_not_raise(self, azurite_container):
        container_name, conn_str = azurite_container
        dfs = download_csv(conn_str, container_name)
        metadata = build_dataset_metadata(dfs)
        assert isinstance(metadata, str)

    def test_case_insensitive_csv_extension(self, azurite_container):
        """Blob names ending in .CSV (uppercase) should also be downloaded."""
        container_name, conn_str = azurite_container
        cc = BlobServiceClient.from_connection_string(conn_str).get_container_client(container_name)
        cc.upload_blob("DATA.CSV", PROJECTS_CSV.encode())
        dfs = download_csv(conn_str, container_name)
        assert "DATA.CSV" in dfs
