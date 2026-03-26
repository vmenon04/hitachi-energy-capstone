import os
import requests
import msal
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

load_dotenv()

STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME")

# MSAL Configuration - client credentials (no human interaction required)
CLIENT_ID = os.environ.get("SHAREPOINT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SHAREPOINT_CLIENT_SECRET")
TENANT_ID = os.environ.get("SHAREPOINT_TENANT_ID")
# .default tells Entra to grant all application permissions configured on the app registration
SCOPES = ["https://graph.microsoft.com/.default"]

def get_access_token():
    """
    Acquires a Microsoft Graph access token using the OAuth 2.0 client credentials
    flow. No human interaction is required, making this safe for unattended
    Azure Container Apps deployments.
    """
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=SCOPES)
    if result and "access_token" in result:
        return result["access_token"]
    error = result.get("error_description", result.get("error", "Unknown error")) if result else "No response"
    raise Exception(f"Could not acquire Microsoft Graph token: {error}")

def sharepoint_to_blob(drive_id: str, folder_id: str = "root"):
    """
    The function transfers all files from a SharePoint folder to the Azure 
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

    # Initialize Blob Client
    if not STORAGE_CONNECTION_STRING:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not set in .env")
    
    # Create the BlobServiceClient necessary for interaction with Azure Blob Storage
    client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    blob_client = client.get_container_client(STORAGE_CONTAINER_NAME)

    # Get the list of all files in the specified SharePoint folder (using the drive and folder IDs)
    print(f"Fetching files from SharePoint (Drive: {drive_id}, Folder: {folder_id})...")
    list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children"
    
    response = requests.get(list_url, headers=headers)
    # check API call response status, if not 200, we have a problem.
    if response.status_code != 200:
        print(f"Error fetching files: {response.text}")
        response.raise_for_status()

    # Gets all the items that we got from the previous API request
    items = response.json().get("value", [])
    print(f"Found {len(items)} items in the folder.")

    #Loop through all the files in the directory and send the CSV/Excel Files to Azure Blob Storage
    for item in items:
        # Check the file extension to find CSVs/Excel files
        # Can add any file extensions to this list later based on what inputs we are expecting.
        if "file" in item and (item["name"].endswith(".csv") or item["name"].endswith(".CSV") 
                            or item["name"].endswith(".xlsx") or item["name"].endswith(".XLSX") 
                            or item["name"].endswith(".xls") or item["name"].endswith(".XLS")):
            name = item["name"]
            file_id = item["id"]

            # Send API call to get the content of the CSV/Excel file
            print(f"Reading {name}...")            
            read_file_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/content"
            file_response = requests.get(read_file_url, headers=headers, stream=True)
            file_response.raise_for_status() # check API call response status

            # Send the content of the CSV/Excel file to Azure Blob Storage
            new_blob = blob_client.get_blob_client(name)
            new_blob.upload_blob(file_response.content, overwrite=True)
            print(f"Successfully Read and Transferred {name} to Azure Blob Storage")
    
    print("Finished Transferring Files from SharePoint folder to Azure Blob Storage")

def main():
    try:
        drive_id = os.environ.get("SHAREPOINT_DRIVE_ID")
        folder_id = os.environ.get("SHAREPOINT_FOLDER_ID", "root")

        if not drive_id:
            raise ValueError("SHAREPOINT_DRIVE_ID environment variable is not set.")

        sharepoint_to_blob(drive_id, folder_id)
        
    except Exception as e:
        print(f"\nError in the process: {e}")
        exit(1) # Exit with error code for automated workflows

if __name__ == "__main__":
    main()
