# Azure App Registration for SharePoint/OneDrive Ingestion

The data fetching pipeline uses the Microsoft Graph API to read files from
OneDrive/SharePoint and transfer them to Azure Blob Storage. Authentication
differs slightly between personal Microsoft accounts (development) and work/school
accounts (production).

## 1. Create the App Registration

1. Go to [portal.azure.com](https://portal.azure.com)
2. Navigate to **Microsoft Entra ID → App registrations → New registration**
3. Configure:
   - **Name**: anything descriptive, e.g. `hitachi-datafetch`
   - **Supported account types**:
     - Personal account: *Personal Microsoft accounts only*
     - Work account: *Accounts in this organizational directory only*
4. Click **Register**
5. From the Overview page, copy the **Application (client) ID** → this is `SHAREPOINT_CLIENT_ID`
6. Also copy the **Directory (tenant) ID** → this is `SHAREPOINT_TENANT_ID` (work accounts only)

## 2. Configure API Permissions

### Personal account
1. Go to **API permissions → Add a permission → Microsoft Graph → Delegated permissions**
2. Add `Files.Read.All`
3. Go to **Authentication → Advanced settings → Allow public client flows → Enabled**

### Work/school account
1. Go to **API permissions → Add a permission → Microsoft Graph → Application permissions**
2. Add `Files.Read.All` (or `Sites.Read.All` if accessing SharePoint document libraries)
3. Click **Grant admin consent** (required for application permissions to take effect)

## 3. Create a Client Secret (work accounts only)

1. Go to **Certificates & secrets → New client secret**
2. Set an expiry and click **Add**
3. Copy the **Value** immediately — it is only shown once
4. Store it as the GitHub Actions secret `SHAREPOINT_CLIENT_SECRET` and in Key Vault as `sharepoint-client-secret`

## 4. Find the Drive and Folder IDs

Use [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer) signed in with the account that owns the data:

```
GET https://graph.microsoft.com/v1.0/me/drives
```

Copy the `id` of the drive → `SHAREPOINT_DRIVE_ID`.

> If an `Unauthorized` error appears, navigate to Modify Permissions and consent to all.

To find a folder inside the drive:
```
GET https://graph.microsoft.com/v1.0/me/drive/root/children
```
Copy the `id` of the target folder → `SHAREPOINT_FOLDER_ID` (or just set `SHAREPOINT_FOLDER_NAME` and let the code resolve it automatically).

## 5. Environment Variables Summary

| Variable | Personal account | Work account |
|---|---|---|
| `SHAREPOINT_CLIENT_ID` | Required | Required |
| `SHAREPOINT_TENANT_ID` | Not used | Required |
| `SHAREPOINT_CLIENT_SECRET` | Not used | Required |
| `SHAREPOINT_DRIVE_ID` | Required | Required |
| `SHAREPOINT_FOLDER_NAME` | Optional (folder name to ingest) | Optional |
| `AZURE_KEYVAULT_URI` | Required locally for token cache | Not needed |

For cloud deployment, store the following as **GitHub Actions secrets** (Settings → Secrets and variables → Actions):

| Account type | Required GitHub Actions secrets |
|---|---|
| Personal | `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_DRIVE_ID` |
| Work/school | `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_DRIVE_ID`, `SHAREPOINT_CLIENT_SECRET`, `SHAREPOINT_TENANT_ID` |

`AZURE_KEYVAULT_URI` is injected automatically by Bicep and does not need to be a GitHub Actions secret.
