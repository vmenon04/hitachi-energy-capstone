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
    storageAccountName: '${prefix}storage${uniqueSuffix}'
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

// get the output from the modules and show it to us
output aiResourceName string = aiModule.outputs.aiResourceName
output storageName string = storageModule.outputs.storageAccountName
