// ai-foundry.bicep
param location string
param aiResourceName string
param projectName string

resource aiResource 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiResourceName
  location: location
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: aiResourceName
    publicNetworkAccess: 'Enabled'
    restore: true
  }
}

// deploy the model
resource gptDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiResource
  name: 'claude-haiku-4-5'
  properties: {
    model: {
      format: 'Claude'
      name: 'claude-haiku-4-5'
      version: '2024-12-19'
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: 1
  }
}

// ai foundry project
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: aiResource
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'Hitachi BI Analysis'
  }
}

output aiResourceName string = aiResource.name
