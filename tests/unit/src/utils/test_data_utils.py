import pytest
import io
import pandas as pd

from src.utils.data_utils import download_csv, build_dataset_metadata

@pytest.fixture
def mock_blob_storage(mocker):
	csv_one = pd.DataFrame({"id": [1, 2], "name": ["Alpha", "Beta"]})
	csv_two = pd.DataFrame({"status": ["open", "closed"], "count": [5, 7]})

	blob_payloads = {
		"project_data.csv": csv_one.to_csv(index=False).encode("utf-8"),
		"notes.txt": b"ignore this non-csv blob",
		"issues.CSV": csv_two.to_csv(index=False).encode("utf-8"),
	}

	blob_csv_1 = mocker.Mock()
	blob_csv_1.name = "project_data.csv"
	blob_txt = mocker.Mock()
	blob_txt.name = "notes.txt"
	blob_csv_2 = mocker.Mock()
	blob_csv_2.name = "issues.CSV"
	listed_blobs = [blob_csv_1, blob_txt, blob_csv_2]

	container_client = mocker.Mock(name="container_client")
	container_client.list_blobs.return_value = listed_blobs

	def test_get_blob_client(blob_name):
		blob_client = mocker.Mock()
		stream = mocker.Mock()
		stream.readall.return_value = blob_payloads[blob_name]
		blob_client.download_blob.return_value = stream
		return blob_client

	container_client.get_blob_client.side_effect = test_get_blob_client

	service_client = mocker.Mock(name="blob_service_client")
	service_client.get_container_client.return_value = container_client

	from_connection_string = mocker.patch(
		"src.utils.data_utils.BlobServiceClient.from_connection_string",
		return_value=service_client,
	)

	return {
		"from_connection_string": from_connection_string,
		"service_client": service_client,
		"container_client": container_client,
		"expected_csvs": {"project_data.csv": csv_one, "issues.CSV": csv_two},
	}


class TestDownloadCSV:
	def test_downloads_only_csv_blobs(self, mock_blob_storage):
		result = download_csv("UseDevelopmentStorage=true", "test-container")

		assert set(result.keys()) == {"project_data.csv", "issues.CSV"}
		assert "notes.txt" not in result

		pd.testing.assert_frame_equal(
			result["project_data.csv"],
			mock_blob_storage["expected_csvs"]["project_data.csv"],
		)
		pd.testing.assert_frame_equal(
			result["issues.CSV"],
			mock_blob_storage["expected_csvs"]["issues.CSV"],
		)

		mock_blob_storage["from_connection_string"].assert_called_once_with(
			"UseDevelopmentStorage=true"
		)
		mock_blob_storage["service_client"].get_container_client.assert_called_once_with(
			container="test-container"
		)
		assert mock_blob_storage["container_client"].get_blob_client.call_count == 2

	def test_returns_empty_dict_when_no_csv_blobs_exist(self, mock_blob_storage, mocker):
		non_csv_blob = mocker.Mock()
		non_csv_blob.name = "readme.md"
		mock_blob_storage["container_client"].list_blobs.return_value = [non_csv_blob]

		result = download_csv("UseDevelopmentStorage=true", "test-container")

		assert result == {}
		mock_blob_storage["container_client"].get_blob_client.assert_not_called()


class TestBuildDatasetMetadata:
	def test_includes_dataset_shapes_and_column_dtypes(self):
		dfs = {
			"users.csv": pd.DataFrame({"id": [1, 2], "name": ["A", "B"]}),
			"issues.csv": pd.DataFrame({"open": [True, False], "count": [3, 4]}),
		}

		metadata = build_dataset_metadata(dfs)

		assert "Dataset: users.csv" in metadata
		assert "Rows: 2, Columns: 2" in metadata
		assert "  - id (int64)" in metadata
		assert ("  - name (object)" in metadata) or ("  - name (str)" in metadata)
		assert "Dataset: issues.csv" in metadata
		assert "  - open (bool)" in metadata