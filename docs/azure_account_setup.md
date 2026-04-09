# Azure Account Setup & Migration Guide

This guide covers setting up a brand-new Azure (personal) account for this project, including creating all required resources, configuring GitHub Actions, and re-establishing local development access.

---

## 1. Create & Prepare Your Azure Account

1. Go to [portal.azure.com](https://portal.azure.com) and sign in with your new personal Microsoft account.
3. Copy your **Subscription ID** since you'll need it throughout.

---

## 2. Create the Resource Group

1. In the Azure Portal: **Resource groups → Create**.
2. Name: `Hitachi-RG` (must match the `RESOURCE_GROUP` env var in [`deploy.yml`](../.github/workflows/deploy.yml)).
3. Region: `East US` (matches the `LOCATION` env var).
4. Click **Review + Create → Create**.

---

## 3. Create a Service Principal for GitHub Actions

GitHub Actions authenticates to Azure using a service principal stored in `AZURE_CREDENTIALS`.

```bash
# Log in with your new account
az login

# Set your subscription
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"

# Create the service principal with Contributor access scoped to the resource group
az ad sp create-for-rbac \
  --name "hitachi-github-actions" \
  --role Contributor \
  --scopes /subscriptions/<YOUR_SUBSCRIPTION_ID>/resourceGroups/Hitachi-RG \
  --sdk-auth
```

This outputs JSON like:

```json
{
  "clientId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "clientSecret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "subscriptionId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "tenantId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "activeDirectoryEndpointUrl": "https://login.microsoftonline.com",
  "resourceManagerEndpointUrl": "https://management.azure.com/",
  ...
}
```

> **Important:** Copy the entire JSON output. This is the value for the `AZURE_CREDENTIALS` GitHub Actions secret.

### Additional role assignment

The service principal also needs **User Access Administrator** on the resource group so it can assign RBAC roles (e.g., Key Vault Secrets Officer to the managed identity) during deployment:

```bash
az role assignment create \
  --role "User Access Administrator" \
  --assignee "36dbfc6d-09c2-410c-99d8-f4b77767a5f4" \
  --scope /subscriptions/70ed3384-26ed-4819-83b4-329e5f99d856/resourceGroups/Hitachi-RG
```

---

## 4. Register Required Azure Resource Providers (Optional)

The Contributor role granted in step 3 includes `*/register/action`, so Azure will **auto-register** providers when the Bicep deployment first creates a resource of that type. You can skip this step entirely.

The only edge case: on a brand-new subscription, auto-registration can take a minute mid-deployment and occasionally causes a `MissingSubscriptionRegistration` error. If that happens, just re-run the deployment, it will succeed once registration completes.

If you'd rather avoid that risk, pre-register manually:

```bash
az provider register --namespace Microsoft.App                     # Container Apps
az provider register --namespace Microsoft.ContainerRegistry       # ACR
az provider register --namespace Microsoft.CognitiveServices       # AI Services / Foundry
az provider register --namespace Microsoft.Communication           # Communication Services (email)
az provider register --namespace Microsoft.KeyVault                # Key Vault
az provider register --namespace Microsoft.Storage                 # Storage Accounts
az provider register --namespace Microsoft.OperationalInsights     # Log Analytics
az provider register --namespace Microsoft.ManagedIdentity         # Managed Identity
```

Check registration status:

```bash
az provider show --namespace Microsoft.App --query "registrationState" -o tsv
```

Wait until all show `Registered` before deploying (can take 1–5 minutes each).

---

## 5. Update GitHub Actions Secrets

Go to your GitHub repo → **Settings → Secrets and variables → Actions** and update/create:

| Secret | Value | Notes |
|---|---|---|
| `AZURE_CREDENTIALS` | The full JSON from step 3 | Contains subscriptionId, clientId, clientSecret, tenantId |
| `SHAREPOINT_CLIENT_ID` | App registration client ID | See [App Registration](azure_app_registration.md), you'll need a new one on the new account |
| `SHAREPOINT_DRIVE_ID` | OneDrive drive ID | Fetch via Graph Explorer (see step 7) |
| `SHAREPOINT_CLIENT_SECRET` | *(empty or omit)* | Only needed for work/school accounts |
| `SHAREPOINT_TENANT_ID` | *(empty or omit)* | Only needed for work/school accounts |

> **Key point:** Since you're on a personal account, you only need `SHAREPOINT_CLIENT_ID` and `SHAREPOINT_DRIVE_ID` for SharePoint integration. `SHAREPOINT_CLIENT_SECRET` and `SHAREPOINT_TENANT_ID` can be left empty.

---

## 6. Create a New App Registration (for SharePoint/OneDrive)

Since you have a new Azure account, you need a new app registration. Follow the full steps in [azure_app_registration.md](azure_app_registration.md). Summary for personal accounts:

1. **Entra ID → App registrations → New registration**
   - Name: `hitachi-datafetch`
   - Supported account types: **Personal Microsoft accounts only**
2. **API permissions → Microsoft Graph → Delegated → `Files.Read.All`**
3. **Authentication → Allow public client flows → Yes**
4. Copy the **Application (client) ID** → this is your new `SHAREPOINT_CLIENT_ID`

---

## 7. Get Your OneDrive Drive ID and Folder Info

1. Go to [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer)
2. Sign in with your new personal Microsoft account
3. Run:
   ```
   GET https://graph.microsoft.com/v1.0/me/drives
   ```
4. Copy the `id` of your drive → this is `SHAREPOINT_DRIVE_ID`
5. To verify folder access:
   ```
   GET https://graph.microsoft.com/v1.0/me/drive/root/children
   ```
6. Upload your data files (`.csv`, `.xlsx`) to a folder in OneDrive (default expected name: `Project_Data`)

---

## 8. Run the Initial Infrastructure Deployment

You can either trigger the GitHub Actions workflow or deploy manually:

### Option A: GitHub Actions (recommended)
1. Push to the `infrastructure`, `development`, or `main` branch, or trigger manually via **Actions → Deploy to Azure → Run workflow**.
2. The pipeline will:
   - Run all tests
   - Deploy Bicep templates (Storage, AI Foundry, Key Vault, Communication Services, ACR, Container App Environment)
   - Assign RBAC roles

### Option B: Manual CLI deployment
```bash
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"

az deployment group create \
  --resource-group Hitachi-RG \
  --template-file infra/main.bicep \
  --parameters \
    location=eastus \
    aiLocation=eastus2 \
    deployContainerJob=false \
    sharepointClientId=<YOUR_SHAREPOINT_CLIENT_ID> \
    sharepointDriveId=<YOUR_SHAREPOINT_DRIVE_ID>
```

---

## 9. Store the SharePoint Token Cache (Personal Account)

For personal accounts, the SharePoint/OneDrive integration uses device-code auth with a token cache stored in Key Vault. This is a one-time interactive step:

1. Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```
2. Fill in at minimum:
   ```
   SHAREPOINT_CLIENT_ID=<your new app registration client ID>
   AZURE_KEYVAULT_URI=https://<your-keyvault-name>.vault.azure.net/
   ```
   Find your Key Vault name:
   ```bash
   az keyvault list --resource-group Hitachi-RG --query "[0].name" -o tsv
   ```
3. Give yourself Key Vault access:
   ```bash
   az role assignment create \
     --role "Key Vault Secrets Officer" \
     --assignee "<your-azure-email>" \
     --scope /subscriptions/<SUB_ID>/resourceGroups/Hitachi-RG/providers/Microsoft.KeyVault/vaults/<KV_NAME>
   ```
4. Run the login script:
   ```bash
   az login
   python src/datafetching/login_and_store_token.py
   ```
   This opens a browser for device-code auth, then stores the MSAL token cache in Key Vault (secret: `sharepoint-token-cache`). The refresh token is valid for ~90 days — re-run this script if it expires.

---

## 10. Set Up Local Development Environment

1. Create and populate your `.env` file. After infrastructure is deployed, fill in the values:

   ```bash
   # Get values from deployed resources
   KV_NAME=$(az keyvault list --resource-group Hitachi-RG --query "[0].name" -o tsv)

   # AI endpoint and key
   az keyvault secret show --vault-name "$KV_NAME" --name azure-ai-project-endpoint --query value -o tsv
   az keyvault secret show --vault-name "$KV_NAME" --name azure-ai-project-api-key --query value -o tsv

   # Storage connection string
   az keyvault secret show --vault-name "$KV_NAME" --name azure-storage-connection-string --query value -o tsv

   # Communication Services connection string
   az keyvault secret show --vault-name "$KV_NAME" --name acs-connection-string --query value -o tsv

   # Email from address
   az keyvault secret show --vault-name "$KV_NAME" --name email-from-address --query value -o tsv
   ```

2. Your `.env` should look like:
   ```
   AZURE_AI_PROJECT_ENDPOINT=https://<name>.openai.azure.com/
   AZURE_AI_PROJECT_API_KEY=<key>
   AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
   AZURE_STORAGE_CONTAINER_NAME=bi-data
   AZURE_REPORTS_CONTAINER_NAME=bi-reports
   SHAREPOINT_CLIENT_ID=<your app client id>
   SHAREPOINT_DRIVE_ID=<your drive id>
   SHAREPOINT_FOLDER_NAME=Project_Data
   AZURE_KEYVAULT_URI=https://<kv-name>.vault.azure.net/
   ACS_CONNECTION_STRING=endpoint=https://...
   EMAIL_FROM_ADDRESS=DoNotReply@<acs-domain>
   EMAIL_RECIPIENT=hitachiseniordesign@outlook.com
   ```

---

## 11. Verify Everything Works

### Infrastructure
```bash
# List deployed resources
az resource list --resource-group Hitachi-RG --output table
```

You should see:
- Storage account
- AI Services (Cognitive Services)
- Key Vault
- Communication Service + Email Service
- Container Registry
- Container App Environment
- Log Analytics workspace
- Managed Identity

### Application (local run)
```bash
# Activate your venv
source venv/bin/activate

# Run the main pipeline
python src/main.py
```

### Tests
```bash
pytest tests/unit/ -v
```

---

## Migration Checklist

Use this checklist to make sure nothing is missed:

- [ ] New Azure account created and subscription active
- [ ] Resource group `Hitachi-RG` created in `East US`
- [ ] *(Optional)* Resource providers pre-registered — auto-registered by Bicep on first deploy; only needed if deployment fails with `MissingSubscriptionRegistration`
- [ ] Service principal created with **Contributor** + **User Access Administrator** on the resource group
- [ ] `AZURE_CREDENTIALS` GitHub secret updated with new service principal JSON
- [ ] New Entra ID app registration created (personal account type)
- [ ] `SHAREPOINT_CLIENT_ID` GitHub secret updated
- [ ] `SHAREPOINT_DRIVE_ID` GitHub secret updated (from Graph Explorer)
- [ ] Old `SHAREPOINT_CLIENT_SECRET` and `SHAREPOINT_TENANT_ID` cleared (unless using work account)
- [ ] Infrastructure deployed via GitHub Actions or CLI
- [ ] Key Vault RBAC assigned to your personal account
- [ ] SharePoint token cache stored via `login_and_store_token.py`
- [ ] `.env` file populated with new values from Key Vault
- [ ] Data files uploaded to OneDrive `Project_Data` folder
- [ ] Local `python src/main.py` runs end-to-end
- [ ] GitHub Actions deployment pipeline passes

---

## Resources Provisioned by Bicep

| Resource | Bicep Module | Purpose |
|---|---|---|
| Storage Account (+ `bi-data`, `bi-reports` containers) | `storage.bicep` | Data ingestion and report output |
| Azure AI Services + GPT deployment | `ai-foundry.bicep` | LLM-powered insight generation |
| Communication Service + Email Domain | `communication.bicep` | Automated email delivery |
| Key Vault (RBAC-enabled) | `keyvault.bicep` | Centralized secret management |
| Container Registry | `container.bicep` | Docker image storage |
| Container App Environment + Job | `container.bicep` | Scheduled daily pipeline (8 AM UTC) |
| Log Analytics Workspace | `container.bicep` | Job execution logging |
| User-Assigned Managed Identity | `main.bicep` | Secure service-to-service auth |

---

## Troubleshooting

### "Resource provider not registered"
Run the `az provider register` commands from step 4 and wait for them to complete.

### "Authorization failed" during deployment
Ensure your service principal has both **Contributor** and **User Access Administrator** roles on the resource group.

### "Key Vault access denied" locally
Assign yourself the **Key Vault Secrets Officer** role (step 9.3) and ensure you've run `az login`.

### Token cache expired (SharePoint stops syncing)
Re-run `python src/datafetching/login_and_store_token.py` — the refresh token expires after ~90 days of inactivity.

### AI model deployment fails
Azure AI Services (`eastus2`) may have capacity constraints. If `gpt-5.4-mini` fails to deploy, check regional availability in the Azure Portal under **AI Services → Model deployments**.

