// main.bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param aiLocation string = location
param prefix string = 'hitachi'
param deployContainerJob bool = true
param jobImage string = ''
@secure()
param sharepointClientSecret string = ''
param sharepointClientId string = ''
param sharepointTenantId string = ''
param sharepointDriveId string = ''
param sharepointFolderId string = 'root'
param sharepointFolderName string = 'Project_Data'

// create a unique suffix to avoid naming collisions
var uniqueSuffix = uniqueString(resourceGroup().id)
// sharepointEnabled: base SharePoint config present (personal or work account).
// sharepointWorkEnabled: full work-account config present (adds KV client-secret reference).
var sharepointEnabled = !empty(sharepointClientId) && !empty(sharepointDriveId)
var sharepointWorkEnabled = sharepointEnabled && !empty(sharepointTenantId)

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
    location: aiLocation
    aiResourceName: '${prefix}-fdy-${uniqueSuffix}'
    projectName: 'hitachi-bi-project'
  }
}

module commModule 'communication.bicep' = {
  name: 'communication-deployment'
  params: {
    communicationServiceName: '${prefix}-comm-${uniqueSuffix}'
    emailServiceName: '${prefix}-email-${uniqueSuffix}'
  }
}

// Reference the deployed ACS resource to call listKeys() here rather than
// in an output (outputs-should-not-contain-secrets linter rule).
// The name must be a compile-time expression; module outputs are not available
// at deployment start for existing resource references.
resource commServiceRef 'Microsoft.Communication/communicationServices@2023-04-01' existing = {
  name: '${prefix}-comm-${uniqueSuffix}'
}

module kvModule 'keyvault.bicep' = {
  name: 'keyvault-deployment'
  dependsOn: [commModule]
  params: {
    location: location
    keyVaultName: 'kv${uniqueSuffix}'
    storageConnectionString: storageModule.outputs.storageConnectionString
    storageContainerName: storageModule.outputs.csvContainerName
    aiApiKey: aiModule.outputs.aiApiKey
    aiEndpoint: aiModule.outputs.aiEndpoint
    acsConnectionString: commServiceRef.listKeys().primaryConnectionString
    emailFromAddress: 'DoNotReply@${commModule.outputs.emailDomainName}'
    sharepointEnabled: sharepointWorkEnabled
    sharepointClientSecret: sharepointClientSecret
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
    managedIdentityPrincipalId: managedIdentity.properties.principalId
    managedIdentityClientId: managedIdentity.properties.clientId
    keyVaultUri: kvModule.outputs.keyVaultUri
    emailRecipient: 'hitachiseniordesign@outlook.com'
    sharepointEnabled: sharepointEnabled
    sharepointWorkEnabled: sharepointWorkEnabled
    sharepointClientId: sharepointClientId
    sharepointTenantId: sharepointTenantId
    sharepointDriveId: sharepointDriveId
    sharepointFolderId: sharepointFolderId
    sharepointFolderName: sharepointFolderName
  }
}

output aiResourceName string = aiModule.outputs.aiResourceName
output storageName string = storageModule.outputs.storageAccountName
output acrLoginServer string = containerModule.outputs.loginServer
output keyVaultName string = kvModule.outputs.keyVaultName
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
output communicationServiceName string = commModule.outputs.communicationServiceName
output emailFromAddress string = 'DoNotReply@${commModule.outputs.emailDomainName}'
