from pathlib import Path

import pytest
import unittest.mock

from src.datafetching import refresh_extraction as extraction

def test_get_access_token_personal(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", None)
    monkeypatch.setattr(extraction, "_get_token_from_kv_cache", lambda: "token")

    assert extraction.get_access_token() == "token"

def test_get_access_token_work(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", "test")
    monkeypatch.setattr(extraction, "_get_token_client_credentials", lambda: "token")

    assert extraction.get_access_token() == "token"

def test_get_token_client_credentials():
    assert False

def test_get_token_from_kv_cache():
    assert False

def test_resolve_folder_id(mocker):
    response = mocker.Mock()
    response.json.return_value = {"value": [{"name": "Folder", "id": "5634234", "folder": {}}]}
    response.raise_for_status.return_value = None
    mocker.patch("src.datafetching.refresh_extraction.requests.get", return_value=response)

    result = extraction._resolve_folder_id("base", "Folder", {})
    assert result == "5634234"

def test_resolve_folder_id_error(mocker):
    response = mocker.Mock()
    response.json.return_value = {"value": []}
    response.raise_for_status.return_value = None
    mocker.patch("src.datafetching.refresh_extraction.requests.get", return_value=response)

    with pytest.raises(ValueError):
        extraction._resolve_folder_id("base", "Missing", {})

def test_graph_base_work(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", "secret")
    assert extraction._graph_base("drive") == "https://graph.microsoft.com/v1.0/drives/drive"

def test_graph_base_personal(monkeypatch):
    monkeypatch.setattr(extraction, "CLIENT_SECRET", None)
    assert extraction._graph_base("drive") == "https://graph.microsoft.com/v1.0/me/drive"

def test_sharepoint_to_blob():
    assert False
