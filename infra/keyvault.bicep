param location string
param keyVaultName string

param managedIdentityPrincipalId string // from the user-assigned managed identity created in main.bicep

// secret values sourced from sibling module outputs in main.bicep.
@secure() // the @secure() ensures they are masked in deployment logs.
param storageConnectionString string
param storageContainerName string
@secure()
param aiApiKey string
param aiEndpoint string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// this is the built-in role for "Key Vault Secrets User" which grants read access to secrets
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e0'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentityPrincipalId, kvSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      kvSecretsUserRoleId
    )
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource secretStorageConnStr 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'azure-storage-connection-string'
  properties: { value: storageConnectionString }
}

resource secretStorageContainerName 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'azure-storage-container-name'
  properties: { value: storageContainerName }
}

resource secretAiApiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'azure-ai-project-api-key'
  properties: { value: aiApiKey }
}

resource secretAiEndpoint 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'azure-ai-project-endpoint'
  properties: { value: aiEndpoint }
}

output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
