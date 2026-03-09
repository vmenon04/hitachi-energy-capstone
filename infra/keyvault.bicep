param location string
param keyVaultName string

// secret values sourced from sibling module outputs in main.bicep.
@secure() // the @secure() ensures they are masked in deployment logs.
param storageConnectionString string
param storageContainerName string
@secure()
param aiApiKey string
param aiEndpoint string
param smtpEndpoint string
param smtpPort string
param smtpUsername string
param emailFromAddress string

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

resource secretSmtpEndpoint 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'smtp-endpoint'
  properties: { value: smtpEndpoint }
}

resource secretSmtpPort 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'smtp-port'
  properties: { value: smtpPort }
}

resource secretSmtpUsername 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'smtp-username'
  properties: { value: smtpUsername }
}

resource secretEmailFromAddress 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'email-from-address'
  properties: { value: emailFromAddress }
}

output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output keyVaultId string = keyVault.id
