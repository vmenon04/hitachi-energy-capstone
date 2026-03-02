// ai-foundry.bicep
param location string
param aiResourceName string
param projectName string

resource aiResource 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aiResourceName
  location: 'eastus2'
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
  }
}

// deploy the model
resource gptDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiResource
  name: 'gpt-4.1-mini'
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      version: '2025-04-14'
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
  location: 'eastus2'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'Hitachi BI Analysis'
  }
}

output aiResourceName string = aiResource.name
