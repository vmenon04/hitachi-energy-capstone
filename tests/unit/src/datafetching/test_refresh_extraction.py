from pathlib import Path

import pytest
import unittest.mock

from src.datafetching import refresh_extraction as extraction

""" Test that ensures get_access_token works for personal accounts """
def test_get_access_token_personal(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", None)
    monkeypatch.setattr(extraction, "_get_token_from_kv_cache", lambda: "token")

    assert extraction.get_access_token() == "token"

""" Test that ensures get_access_token works for work accounts """
def test_get_access_token_work(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", "test")
    monkeypatch.setattr(extraction, "_get_token_client_credentials", lambda: "token")

    assert extraction.get_access_token() == "token"

""" Test that ensures that get_token_client_credentials returns a valid access token """
def test_get_token_client_credentials(mocker):
    app = mocker.Mock()
    app.acquire_token_for_client.return_value = {"access_token": "testtest"}
    mocker.patch( "src.datafetching.refresh_extraction.msal.ConfidentialClientApplication", return_value = app)
    token = extraction._get_token_client_credentials()
    assert token == "testtest"

""" Test that ensures that get_token_client_credentials raises an exception """
def test_get_token_client_credentials_failure(mocker):
    app = mocker.Mock()
    app.acquire_token_for_client.return_value = {"error": "error"}
    mocker.patch( "src.datafetching.refresh_extraction.msal.ConfidentialClientApplication", return_value = app)
    with pytest.raises(Exception):
        extraction._get_token_client_credentials()

""" Test that ensures that get_token_from_kv_cache returns a valid token and updates the Key Vault """
def test_get_token_from_kv_cache(monkeypatch, mocker):
    monkeypatch.setenv("AZURE_KEYVAULT_URI", "https://testkv")
    secret = mocker.Mock()
    secret = mocker.Mock(value = "cache")
    kv = mocker.Mock()
    kv.get_secret.return_value = secret
    mocker.patch("src.datafetching.refresh_extraction.SecretClient", return_value = kv)
    
    cache = mocker.Mock()
    cache.has_state_changed = True
    cache.serialize.return_value = "new cache"
    mocker.patch("src.datafetching.refresh_extraction.msal.SerializableTokenCache", return_value = cache)
    
    app = mocker.Mock()
    app.get_accounts.return_value = [{"id": "account1"}]
    app.acquire_token_silent.return_value = {"access_token": "token"}
    mocker.patch("src.datafetching.refresh_extraction.msal.PublicClientApplication", return_value = app)

    token = extraction._get_token_from_kv_cache()
    assert token == "token"

""" Test that ensures that the correct folder id is returned with the resolve_folder_id function """
def test_resolve_folder_id(mocker):
    response = mocker.Mock()
    response.json.return_value = {"value": [{"name": "Folder", "id": "5634234", "folder": {}}]}
    response.raise_for_status.return_value = None
    mocker.patch("src.datafetching.refresh_extraction.requests.get", return_value = response)

    result = extraction._resolve_folder_id("base", "Folder", {})
    assert result == "5634234"

""" Test that ensures that resolve_folder_id throws an error if the specified folder is not found """
def test_resolve_folder_id_error(mocker):
    response = mocker.Mock()
    response.json.return_value = {"value": []}
    response.raise_for_status.return_value = None
    mocker.patch("src.datafetching.refresh_extraction.requests.get", return_value=response)

    with pytest.raises(ValueError):
        extraction._resolve_folder_id("base", "Missing", {})

""" Tests that graph_base returns the correct url for a personal account """
def test_graph_base_personal(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", None)
    assert extraction._graph_base("drive") == "https://graph.microsoft.com/v1.0/me/drive"

""" Tests that graph_base returns the correct url for a work account """
def test_graph_base_work(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", "secret")
    assert extraction._graph_base("drive") == "https://graph.microsoft.com/v1.0/drives/drive"

""" Tests the functionality of sharepoint_to_blob """
def test_sharepoint_to_blob(monkeypatch, mocker):
    monkeypatch.setattr(extraction, "STORAGE_CONNECTION_STRING", "testconnectionstring")
    monkeypatch.setattr(extraction, "STORAGE_CONTAINER_NAME", "testcontainer")
    monkeypatch.setattr(extraction, "FOLDER_NAME", "")

    mocker.patch.object(extraction, "get_access_token", return_value="token")

    response_list = mocker.Mock()
    response_list.status_code = 200
    response_list.json.return_value = {"value": [{"name": "test.csv", "id": "434fh97", "file": {}},{"name": "test.txt", "id": "4d928ny7", "file": {}}]}

    response_files = mocker.Mock()
    response_files.content = b"response"
    response_files.raise_for_status.return_value = None
    mocker.patch("src.datafetching.refresh_extraction.requests.get", side_effect=[response_list, response_files])

    blob = mocker.Mock()
    container = mocker.Mock()
    container.get_blob_client.return_value = blob
    service = mocker.Mock()
    service.get_container_client.return_value = container
    mocker.patch("src.datafetching.refresh_extraction.BlobServiceClient.from_connection_string", return_value = service)
    extraction.sharepoint_to_blob("drive")
    blob.upload_blob.assert_called_once()
    

