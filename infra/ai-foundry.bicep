// ai-foundry.bicep

param location string = 'eastus2'
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
  }
}

// deploy the model
resource gptDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiResource
  name: 'gpt-4o-mini'
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: 100
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
output aiEndpoint string = 'https://${aiResource.properties.customSubDomainName}.openai.azure.com/'

// @secure() masks the value in deployment logs
@secure()
output aiApiKey string = aiResource.listKeys().key1
