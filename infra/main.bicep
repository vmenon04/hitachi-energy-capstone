// main.bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param prefix string = 'hitachi'

// create a unique suffix to avoid naming collisions
var uniqueSuffix = uniqueString(resourceGroup().id)

module storageModule 'storage.bicep' = {
  name: 'storage-deployment'
  params: {
    location: location
    // we name is 'hbi' + uniqueSuffix, which is 16 characters. this is under the 24 char limit for storage account names
    storageAccountName: 'hbi${uniqueSuffix}'
  }
}

module aiModule 'ai-foundry.bicep' = {
  name: 'ai-deployment'
  params: {
    location: location
    aiResourceName: '${prefix}-ai-${uniqueSuffix}'
    projectName: 'hitachi-bi-project'
  }
}

module containerModule 'container.bicep' = {
  params: {
    location: location
    acrName: 'hitachiacr${uniqueSuffix}'
  }
}

// Get the output from the modules and show it to us
output aiResourceName string = aiModule.outputs.aiResourceName
output storageName string = storageModule.outputs.storageAccountName
output acrLoginServer string = containerModule.outputs.loginServer
