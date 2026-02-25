# Infrastructure Documentation

## Overview

The infrastructure is deployed using Azure Bicep templates, which provision resources needed for the BI application including storage and AI services.

## Files

### `main.bicep`
Entry point for infrastructure deployment. Orchestrates the deployment of storage and AI modules with a unique suffix to prevent naming conflicts.

**Key Outputs:**
- `aiResourceName` - Name of the deployed AI resource
- `storageName` - Name of the storage account

### `storage.bicep`
Provisions Azure Storage Account with blob services configured for big data workloads.

**Resources:**
- Storage Account (StorageV2, Standard_LRS)
- Blob Services with Hierarchical Namespace (HNS) enabled
- Container named `bi-data` for CSV storage

### `ai-foundry.bicep`
Deploys Azure AI Foundry resources including Claude Haiku 4.5 model deployment.

**Resources:**
- AI Services account with system-assigned identity
- For now, we have Claude Haiku 4.5 model deployed

## Changing the AI Model

To use a different model, edit `ai-foundry.bicep` and update the deployment resource's `name` and `model.name` properties. For example:

```bicep
resource gptDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiResource
  name: 'claude-haiku-4-5'  // Change this
  properties: {
    model: {
      format: 'Claude'
      name: 'claude-haiku-4-5'  // And this to your desired model
      // ...
```

Check Azure documentation for available models.