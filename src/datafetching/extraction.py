import io
import os
import requests
import pandas as pd
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

load_dotenv()
STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME")

def get_access_token():
    """
    Using the DefaultAzureCredential to try and get a token for MS Graph API
    Trying to use Managed Identity to get the tokens
    """
    credentials = DefaultAzureCredential();
    tokens = credentials.get_token("https://graph.microsoft.com/.default")
    return tokens.token;

def sharepoint_to_blob(drive_id: str, folder_id: str = "root"):
    """
    The function transfers all Excel files from SharePoint to the Azure 
    Blob Storage container using MS Graph API calls

    Args: 
        drive_id: The ID of the SharePoint library to pull from
        folder_id: The ID of the specific folder within SharePoint to pull from 
            (default value of root directory)
    """
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    blob_client = client.get_container_client(STORAGE_CONTAINER_NAME)

    print(f"Fetching files from SharePoint...")
    list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children" 
    response = requests.get(list_url, headers = headers)
    response.raise_for_status()
    files = response.json().get("value", [])

def main():
    print("hi")

if __name__ == "__main__":
    main()