// main.bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param prefix string = 'hitachi'
param deployContainerJob bool = true
param jobImage string = ''

// create a unique suffix to avoid naming collisions
var uniqueSuffix = uniqueString(resourceGroup().id)

// created here so its principalId can be passed to keyvault.bicep for role assignment before the container module runs.
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
    managedIdentityPrincipalId: managedIdentity.properties.principalId
    storageConnectionString: storageModule.outputs.storageConnectionString
    storageContainerName: storageModule.outputs.csvContainerName
    aiApiKey: aiModule.outputs.aiApiKey
    aiEndpoint: aiModule.outputs.aiEndpoint
  }
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
