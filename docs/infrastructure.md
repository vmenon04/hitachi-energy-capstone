# Infrastructure Documentation

## Overview

The infrastructure is deployed using Azure Bicep templates, which provision all
resources needed for the BI pipeline: storage, AI, email, Key Vault, and a
scheduled Container App Job that runs the pipeline on a cron schedule.

Deployment is fully automated via the GitHub Actions workflow in
`.github/workflows/deploy.yml`. The workflow has two jobs:
- **deploy-infra**: provisions or updates all Azure resources
- **deploy-app**: builds and pushes the Docker image, then deploys the Container App Job

## Files

### `main.bicep`
Entry point. Orchestrates all modules and passes outputs between them. Creates
the User-Assigned Managed Identity used by the Container App Job for both ACR
image pull and Key Vault secret access.

**Key parameters (all have defaults; SharePoint params are optional):**
- `deployContainerJob` — set `false` for infra-only deploys, `true` when the image exists
- `sharepointClientId`, `sharepointDriveId` — enables SharePoint ingestion when set
- `sharepointTenantId`, `sharepointClientSecret` — additionally enables work-account mode

**Key outputs:**
- `aiResourceName`, `storageName`, `acrLoginServer`, `keyVaultName`, `managedIdentityPrincipalId`

### `storage.bicep`
Provisions Azure Storage Account with blob services configured for big data workloads.

**Resources:**
- Storage Account (StorageV2, Standard_LRS, HNS enabled)
- `bi-data` container — input CSVs/Excel files
- `bi-reports` container — generated PDF reports

### `ai-foundry.bicep`
Deploys Azure AI Foundry resources with a GPT model deployment.

**Resources:**
- AI Services account
- GPT model deployment (`gpt-5.4-mini`)
- AI project

To use a different model, update the `name` and `model.name` fields in the
`gptDeployment` resource in `ai-foundry.bicep`.

### `keyvault.bicep`
Provisions Azure Key Vault (RBAC-authorised, soft-delete enabled) and stores all
application secrets. Secrets are sourced from sibling module outputs in `main.bicep`
so they are never in plaintext in source control or deployment logs.

**Secrets stored:**
- `azure-storage-connection-string`
- `azure-storage-container-name`
- `azure-ai-project-api-key`
- `azure-ai-project-endpoint`
- `acs-connection-string`
- `email-from-address`
- `sharepoint-client-secret` *(only written when `sharepointWorkEnabled` is true)*
- `sharepoint-token-cache` *(written manually by `login_and_store_token.py` for personal accounts)*

### `communication.bicep`
Provisions Azure Communication Services and a managed email domain for sending
insights emails.

**Resources:**
- Communication Service
- Email Service + Azure-managed domain

### `container.bicep`
Provisions the Container Registry (ACR), Log Analytics workspace, Container App
Enviornment, and the scheduled Container App Job.

The job uses a User-Assigned Managed Identity for:
1. Pulling the image from ACR
2. Reading secrets from Key Vault at deploy time via Key Vault secret references

SharePoint env vars are injected conditionally:
- `sharepointEnabled` (clientId + driveId present): injects `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_DRIVE_ID`, `SHAREPOINT_FOLDER_ID`
- `sharepointWorkEnabled` (also tenantId present): additionally injects `SHAREPOINT_CLIENT_SECRET` (KV ref) and `SHAREPOINT_TENANT_ID`

`AZURE_KEYVAULT_URI` and `AZURE_CLIENT_ID` are always injected so the container
can read/write the `sharepoint-token-cache` secret for personal-account mode.

## Role Assignments

| Principal | Role | Scope | Purpose |
|---|---|---|---|
| User-Assigned MI | AcrPull | ACR | Pull container image |
| User-Assigned MI | Key Vault Secrets Officer | Key Vault | Read secrets + write back token cache |

The Key Vault role assignment is performed in the `deploy-infra` workflow job via
`az role assignment create` after the Bicep deployment completes.

## Adding a New Secret

1. Add a `@secure() param` to `keyvault.bicep`
2. Add the corresponding `resource` block to create the KV secret
3. Pass the value in from `main.bicep` (either from a module output or a new top-level `@secure() param`)
4. Add a `secrets` entry in `container.bicep` pointing to the KV URL
5. Add an `env` entry in `container.bicep` referencing the secret
6. If the value comes from outside Azure, add a GitHub Actions secret and pass it as a Bicep parameter in `deploy.yml`
