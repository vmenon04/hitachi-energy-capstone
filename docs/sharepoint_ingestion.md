# SharePoint / OneDrive Ingestion

This document explains how the data fetching pipeline authenticates, what files it
transfers, and how to set it up for a new environment.

## How it works

`src/datafetching/refresh_extraction.py` runs on a schedule inside a Container App
Job. It:

1. Obtains a Microsoft Graph API access token
2. Resolves the target folder inside the drive (if `SHAREPOINT_FOLDER_NAME` is set)
3. Lists all CSV and Excel files in that folder
4. Uploads them to the Azure Storage `bi-data` container with a blob path that
   mirrors the source folder structure (e.g. `Project_Data/sales.csv`)

The rest of the pipeline then reads from blob storage.

---

## Authentication modes

The script supports two account types, auto-detected at runtime.

### Personal Microsoft account (development / demo)

Personal accounts do not support the OAuth 2.0 client-credentials flow. Instead,
a token is obtained interactively once and persisted as an MSAL cache in Key Vault.
The container reads and refreshes this cache silently on every run.

**One-time setup:**

```bash
# 1. Log in to Azure so the script can write to Key Vault
az login

# 2. Copy .env.example to .env and fill in SHAREPOINT_CLIENT_ID and AZURE_KEYVAULT_URI
cp .env.example .env

# 3. Run the interactive login script (follows device code flow -- opens a browser)
python src/datafetching/login_and_store_token.py
```

The script will prompt you to visit `https://microsoft.com/devicelogin` and enter a
code. After authentication it serialises the MSAL token cache and stores it in Key
Vault as the secret `sharepoint-token-cache`.

**Refresh token lifetime:** Microsoft personal-account refresh tokens are valid for
**up to 90 days** of inactivity. If the pipeline does not run for more than 90 days,
re-run `login_and_store_token.py` to refresh the cache.

### Work / school account (hopefully we can get to production)

Uses the OAuth 2.0 client-credentials flow (app-only, no user interaction). The
container receives `SHAREPOINT_CLIENT_SECRET` and `SHAREPOINT_TENANT_ID` as
environment variables (injected from Key Vault at deploy time).

No manual token caching is required; the container acquires a fresh token on every
run.

---

## Environment variables

Set these in `.env` locally and as GitHub Actions secrets for cloud deployment.

| Variable | Description | Required for |
|---|---|---|
| `SHAREPOINT_CLIENT_ID` | App Registration client ID | Both modes |
| `SHAREPOINT_DRIVE_ID` | OneDrive/SharePoint drive ID | Both modes |
| `SHAREPOINT_FOLDER_ID` | Folder item ID (optional; used if `FOLDER_NAME` not set) | Both modes |
| `SHAREPOINT_FOLDER_NAME` | Name of the folder to ingest (e.g. `Project_Data`) | Both modes |
| `SHAREPOINT_CLIENT_SECRET` | App Registration client secret | Work accounts only |
| `SHAREPOINT_TENANT_ID` | Azure tenant ID | Work accounts only |
| `AZURE_KEYVAULT_URI` | URI of the Key Vault holding secrets and the token cache | Both modes |
| `AZURE_CLIENT_ID` | Client ID of the User-Assigned Managed Identity | Cloud deployment |

`AZURE_KEYVAULT_URI` and `AZURE_CLIENT_ID` are injected automatically by the Bicep
template -- you do not need to set them manually in GitHub Actions.

---

## Microsoft Graph URL differences

| Account type | Drive URL base |
|---|---|
| Personal | `https://graph.microsoft.com/v1.0/me/drive` |
| Work/school | `https://graph.microsoft.com/v1.0/drives/{SHAREPOINT_DRIVE_ID}` |

The helper function `_graph_base()` in `refresh_extraction.py` selects the correct
base automatically: personal mode is used when `SHAREPOINT_CLIENT_SECRET` is not set.

---

## Folder scoping

Setting `SHAREPOINT_FOLDER_NAME` restricts ingestion to a single folder.

**How it works:**
1. The script lists the drive root children via Graph API
2. Finds the folder whose `name` matches `SHAREPOINT_FOLDER_NAME`
3. Lists only files inside that folder
4. Uploads each file with the blob prefix `{SHAREPOINT_FOLDER_NAME}/filename` so
   the source folder is mirrored in blob storage

If `SHAREPOINT_FOLDER_NAME` is empty and `SHAREPOINT_FOLDER_ID` is also empty,
the script falls back to the drive root.

---

## Local testing

```bash
# Make sure .env is populated (copy from .env.example)
cp .env.example .env  # then edit

# Install dependencies
pip install -r requirements.txt

# Run ingestion (will read token from KV for personal accounts)
python src/datafetching/refresh_extraction.py
```

Successful output ends with a line per uploaded file:
```
Uploaded Project_Data/sales.csv to bi-data
Uploaded Project_Data/inventory.xlsx to bi-data
```

---

## Deployment

SharePoint ingestion is enabled at deploy time by passing non-empty values for
`sharepointClientId` and `sharepointDriveId` to the Bicep parameter file or as
`--parameters` overrides in `deploy.yml`. When these are empty (the default), the
Container App Job is deployed without any SharePoint-related secrets or env vars --
so infra-only deploys never fail due to missing SharePoint configuration.

The GitHub Actions workflow reads the following secrets:
- `SHAREPOINT_CLIENT_ID`
- `SHAREPOINT_DRIVE_ID`
- `SHAREPOINT_CLIENT_SECRET` *(leave blank for personal-account mode)*
- `SHAREPOINT_TENANT_ID` *(leave blank for personal-account mode)*

See [azure_app_registration.md](azure_app_registration.md) for how to create and
configure the App Registration.
