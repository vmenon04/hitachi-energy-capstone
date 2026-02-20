param location string
param acrName string
param managedIdentityName string = 'hitachi-mi'
param containerAppEnvName string = 'hitachi-env'
param jobName string = 'hitachi-job'
param jobContainerName string = 'job-runner'
param jobImage string = '${acrName}.azurecr.io/hitachi-app:latest'
param jobCpu int = 1
param jobMemory string = '2Gi'
param replicaTimeout int = 1800
param replicaRetryLimit int = 1
param parallelism int = 1
param replicaCompletionCount int = 1

var containerAppsJobsContributorRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4e3d2b60-56ae-4dc6-a233-09c8e5a82e68'
)

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: managedIdentityName
  location: location
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
  }
}

resource containerAppJob 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: containerAppEnv.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: replicaTimeout
      replicaRetryLimit: replicaRetryLimit
      manualTriggerConfig: {
        parallelism: parallelism
        replicaCompletionCount: replicaCompletionCount
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: jobContainerName
          image: jobImage
          resources: {
            cpu: jobCpu
            memory: jobMemory
          }
        }
      ]
    }
  }
}

resource containerAppJobContributorRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, managedIdentity.id, 'ContainerAppsJobsContributor')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: containerAppsJobsContributorRoleDefinitionId
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer
output containerAppEnvId string = containerAppEnv.id
output containerAppJobId string = containerAppJob.id
output managedIdentityId string = managedIdentity.id
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
output managedIdentityClientId string = managedIdentity.properties.clientId
