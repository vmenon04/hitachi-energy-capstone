// storage.bicep
param location string
param storageAccountName string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS' // this is enough for MVP, we can change it later if needed
  }
  properties: {
    accessTier: 'Hot'
    isHnsEnabled: true // enable a hierarchical namespace (Hns), which is better for big data
  }
}

resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource csvContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobServices
  name: 'bi-data' // this is the folder that shoudl house the CSVs
}

resource reportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobServices
  name: 'bi-reports' // this container stores generated reports
  properties: {
    publicAccess: 'None'
  }
}

output storageAccountName string = storageAccount.name
output reportsContainerName string = reportsContainer.name
