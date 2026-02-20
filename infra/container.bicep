param location string
param acrName string
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

var acrPullRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
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

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, containerAppJob.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: containerAppJob.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer
output containerAppEnvId string = containerAppEnv.id
output containerAppJobId string = containerAppJob.id
