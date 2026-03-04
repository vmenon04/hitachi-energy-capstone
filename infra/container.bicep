param location string
param acrName string
param deployContainerJob bool = true
param containerAppEnvName string = 'hitachi-env'
param logAnalyticsWorkspaceName string = 'hitachi-logs'
param jobName string = 'hitachi-job'
param jobContainerName string = 'job-runner'
param jobImage string = '${acrName}.azurecr.io/hitachi-app:latest'
param jobCpu int = 1
param jobMemory string = '2Gi'
param replicaTimeout int = 1800
param replicaRetryLimit int = 1
param parallelism int = 1
param replicaCompletionCount int = 1
param managedIdentityId string
param keyVaultUri string

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

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

resource containerAppJob 'Microsoft.App/jobs@2024-03-01' = if (deployContainerJob) {
  name: jobName
  location: location
  identity: {
    // SystemAssigned is used by the ACR registry pull (identity: 'system' below).
    // UserAssigned is used for Key Vault secret references at runtime.
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
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

      secrets: [
        {
          name: 'azure-storage-connection-string'
          keyVaultUrl: '${keyVaultUri}secrets/azure-storage-connection-string'
          identity: managedIdentityId
        }
        {
          name: 'azure-storage-container-name'
          keyVaultUrl: '${keyVaultUri}secrets/azure-storage-container-name'
          identity: managedIdentityId
        }
        {
          name: 'azure-ai-project-api-key'
          keyVaultUrl: '${keyVaultUri}secrets/azure-ai-project-api-key'
          identity: managedIdentityId
        }
        {
          name: 'azure-ai-project-endpoint'
          keyVaultUrl: '${keyVaultUri}secrets/azure-ai-project-endpoint'
          identity: managedIdentityId
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
          env: [
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'azure-storage-connection-string' }
            { name: 'AZURE_STORAGE_CONTAINER_NAME',    secretRef: 'azure-storage-container-name' }
            { name: 'AZURE_AI_PROJECT_API_KEY',        secretRef: 'azure-ai-project-api-key' }
            { name: 'AZURE_AI_PROJECT_ENDPOINT',       secretRef: 'azure-ai-project-endpoint' }
          ]
        }
      ]
    }
  }
}

// grant the job's SystemAssigned identity AcrPull on the registry.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // without this the job cannot pull its own image at startup.

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployContainerJob) {
  name: guid(acr.id, containerAppJob.?id ?? '', acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: containerAppJob.?identity.?principalId ?? ''
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer
output containerAppEnvId string = containerAppEnv.id
output containerAppJobId string = deployContainerJob ? containerAppJob.id : ''
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
