// main.bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param prefix string = 'hitachi'
param deployContainerJob bool = true
param jobImage string = ''

// create a unique suffix to avoid naming collisions
var uniqueSuffix = uniqueString(resourceGroup().id)

// created here so its principalId can be used in the Key Vault role assignment below.
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-mi'
  location: location
}

module storageModule 'storage.bicep' = {
  name: 'storage-deployment'
  params: {
    location: location
    storageAccountName: 'hbi${uniqueSuffix}'
  }
}

module aiModule 'ai-foundry.bicep' = {
  name: 'ai-deployment'
  params: {
    aiResourceName: '${prefix}-fdy-${uniqueSuffix}'
    projectName: 'hitachi-bi-project'
  }
}

module kvModule 'keyvault.bicep' = {
  name: 'keyvault-deployment'
  params: {
    location: location
    keyVaultName: 'kv${uniqueSuffix}'
    storageConnectionString: storageModule.outputs.storageConnectionString
    storageContainerName: storageModule.outputs.csvContainerName
    aiApiKey: aiModule.outputs.aiApiKey
    aiEndpoint: aiModule.outputs.aiEndpoint
  }
}

// Role assignment is declared at top-level scope (outside any nested module) so that
// ARM can calculate the resource ID at plan time.
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e0'

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceId('Microsoft.KeyVault/vaults', 'kv${uniqueSuffix}'), managedIdentity.id, kvSecretsUserRoleId)
  scope: keyVaultRef
  dependsOn: [kvModule]
  properties: {
    // subscriptionResourceId() is a pure string function - no runtime lookup needed
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Reference the Key Vault resource so we can scope the role assignment to it
resource keyVaultRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv${uniqueSuffix}'
}

module containerModule 'container.bicep' = {
  name: 'container-deployment'
  params: {
    location: location
    acrName: 'hitachiacr${uniqueSuffix}'
    deployContainerJob: deployContainerJob
    jobImage: empty(jobImage) ? 'hitachiacr${uniqueSuffix}.azurecr.io/hitachi-app:latest' : jobImage
    managedIdentityId: managedIdentity.id
    keyVaultUri: kvModule.outputs.keyVaultUri
  }
}

output aiResourceName string = aiModule.outputs.aiResourceName
output storageName string = storageModule.outputs.storageAccountName
output acrLoginServer string = containerModule.outputs.loginServer
output keyVaultName string = kvModule.outputs.keyVaultName
