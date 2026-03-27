import os
import requests
import msal
import logging
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient

load_dotenv()

logger = logging.getLogger("hitachi_pipeline")

STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME")

CLIENT_ID = os.environ.get("SHAREPOINT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SHAREPOINT_CLIENT_SECRET")  # work accounts only
TENANT_ID = os.environ.get("SHAREPOINT_TENANT_ID")            # work accounts only
# Name of the OneDrive/SharePoint folder to read from, e.g. "Project_Data".
# Files are uploaded to Blob Storage under {FOLDER_NAME}/ to mirror the source path.
# Leave empty to read from the drive root (no prefix added).
FOLDER_NAME = os.environ.get("SHAREPOINT_FOLDER_NAME", "")


def get_access_token():
    """
    Acquires a Microsoft Graph access token.

    - Work account: client credentials flow using SHAREPOINT_CLIENT_SECRET.
      No human interaction required.
    - Personal account: reads the MSAL token cache stored in Key Vault by
      login_and_store_token.py and silently refreshes using the stored refresh
      token. Writes the cache back to Key Vault if it changed.
    """
    if CLIENT_SECRET:
        return _get_token_client_credentials()
    return _get_token_from_kv_cache()


def _get_token_client_credentials():
    """OAuth 2.0 client credentials flow for work/school Entra accounts."""
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if result and "access_token" in result:
        return result["access_token"]
    error = result.get("error_description", result.get("error", "Unknown error")) if result else "No response"
    raise Exception(f"Could not acquire Microsoft Graph token: {error}")


def _get_token_from_kv_cache():
    """
    Delegated token flow for personal Microsoft accounts.
    Reads the serialised MSAL token cache from Key Vault (written once by
    login_and_store_token.py), refreshes the access token silently using the
    stored refresh token, and writes the updated cache back if it changed.
    Locally, DefaultAzureCredential uses `az login`.
    In the container, it uses the User-Assigned Managed Identity via AZURE_CLIENT_ID.
    """
    kv_uri = os.environ.get("AZURE_KEYVAULT_URI")
    if not kv_uri:
        raise ValueError(
            "Neither SHAREPOINT_CLIENT_SECRET (work account) nor AZURE_KEYVAULT_URI "
            "(personal account) is configured."
        )

    kv_client = SecretClient(vault_url=kv_uri, credential=DefaultAzureCredential())
    cached = kv_client.get_secret("sharepoint-token-cache").value

    cache = msal.SerializableTokenCache()
    cache.deserialize(cached)

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority="https://login.microsoftonline.com/consumers",
        token_cache=cache,
    )

    accounts = app.get_accounts()
    if not accounts:
        raise Exception(
            "No accounts in the Key Vault token cache. "
            "Re-run src/datafetching/login_and_store_token.py locally."
        )

    result = app.acquire_token_silent(
        scopes=["https://graph.microsoft.com/Files.Read.All"],
        account=accounts[0],
    )

    if not result or "access_token" not in result:
        raise Exception(
            "Could not refresh the token silently. The refresh token may have expired "
            "(personal account tokens expire after ~90 days of no use). "
            "Re-run src/datafetching/login_and_store_token.py locally."
        )

    if cache.has_state_changed:
        kv_client.set_secret("sharepoint-token-cache", cache.serialize())

    return result["access_token"]

def _resolve_folder_id(base: str, folder_name: str, headers: dict) -> str:
    """Returns the Graph item ID of a named folder at the drive root."""
    resp = requests.get(f"{base}/root/children", headers=headers)
    resp.raise_for_status()
    for item in resp.json().get("value", []):
        if "folder" in item and item["name"] == folder_name:
            return item["id"]
    raise ValueError(
        f"Folder '{folder_name}' not found in the root of your OneDrive. "
        "Check the spelling of SHAREPOINT_FOLDER_NAME."
    )


def _graph_base(drive_id: str) -> str:
    """
    Returns the correct Graph API base path for listing/downloading items.

    Work accounts (client credentials): /drives/{drive_id} — drive ID is required
    and the /drives/ path works correctly against SharePoint document libraries.

    Personal accounts (token cache): /me/drive — the /drives/{id}/items/...
    path raises "ObjectHandle is Invalid" (400) for personal OneDrive; the
    /me/drive/... variant is the only supported form for delegated personal tokens.
    """
    if CLIENT_SECRET:
        return f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
    return "https://graph.microsoft.com/v1.0/me/drive"


def sharepoint_to_blob(drive_id: str, folder_id: str = "root"):
    """
    Transfers all CSV/Excel files from a OneDrive/SharePoint folder to Azure
    Blob Storage using the Microsoft Graph API.

    Args:
        drive_id: Drive ID for work accounts (ignored for personal accounts).
        folder_id: Folder item ID within the drive, or 'root' for the root folder.
    """
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    if not STORAGE_CONNECTION_STRING:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not set in .env")

    client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    blob_client = client.get_container_client(STORAGE_CONTAINER_NAME)

    base = _graph_base(drive_id)

    # Resolve folder by name if SHAREPOINT_FOLDER_NAME is set.
    # This also determines the blob prefix so uploads mirror the source path.
    blob_prefix = ""
    if FOLDER_NAME:
        folder_id = _resolve_folder_id(base, FOLDER_NAME, headers)
        blob_prefix = f"{FOLDER_NAME}/"

    if folder_id == "root":
        list_url = f"{base}/root/children"
    else:
        list_url = f"{base}/items/{folder_id}/children"

    logger.info("Fetching files from OneDrive/SharePoint (Folder: %s)...", FOLDER_NAME or "root")
    response = requests.get(list_url, headers=headers)
    if response.status_code != 200:
        logger.error("Error fetching files: %s", response.text)
        response.raise_for_status()

    items = response.json().get("value", [])
    logger.info("Found %d items in the folder.", len(items))

    for item in items:
        if "file" in item and (item["name"].endswith(".csv") or item["name"].endswith(".CSV")
                            or item["name"].endswith(".xlsx") or item["name"].endswith(".XLSX")
                            or item["name"].endswith(".xls") or item["name"].endswith(".XLS")):
            name = item["name"]
            file_id = item["id"]

            logger.info("Reading %s...", name)
            read_file_url = f"{base}/items/{file_id}/content"
            file_response = requests.get(read_file_url, headers=headers, stream=True)
            file_response.raise_for_status()

            new_blob = blob_client.get_blob_client(f"{blob_prefix}{name}")
            new_blob.upload_blob(file_response.content, overwrite=True)
            logger.info("Successfully transferred %s to Azure Blob Storage (%s%s)", name, blob_prefix, name)

    logger.info("Finished transferring files from OneDrive/SharePoint to Azure Blob Storage")


