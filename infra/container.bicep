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
param managedIdentityPrincipalId string
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
    // UserAssigned is used for both ACR image pull and Key Vault secret references.
    type: 'UserAssigned'
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
          identity: managedIdentityId
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
        {
          name: 'smtp-endpoint'
          keyVaultUrl: '${keyVaultUri}secrets/smtp-endpoint'
          identity: managedIdentityId
        }
        {
          name: 'smtp-port'
          keyVaultUrl: '${keyVaultUri}secrets/smtp-port'
          identity: managedIdentityId
        }
        {
          name: 'smtp-username'
          keyVaultUrl: '${keyVaultUri}secrets/smtp-username'
          identity: managedIdentityId
        }
        {
          name: 'email-from-address'
          keyVaultUrl: '${keyVaultUri}secrets/email-from-address'
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
            { name: 'SMTP_ENDPOINT',                   secretRef: 'smtp-endpoint' }
            { name: 'SMTP_PORT',                       secretRef: 'smtp-port' }
            { name: 'SMTP_USERNAME',                   secretRef: 'smtp-username' }
            { name: 'EMAIL_FROM_ADDRESS',              secretRef: 'email-from-address' }
          ]
        }
      ]
    }
  }
}

// Grant the User Assigned Managed Identity AcrPull on the registry.
// This is intentionally NOT gated on deployContainerJob so the permission exists
// before the Container App Job is first created, avoiding RBAC propagation races.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentityId, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = acr.properties.loginServer
output containerAppEnvId string = containerAppEnv.id
output containerAppJobId string = deployContainerJob ? containerAppJob.id : ''
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
