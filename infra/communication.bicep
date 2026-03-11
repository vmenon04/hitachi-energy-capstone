// communication.bicep

param communicationServiceName string
param emailServiceName string
param domainName string = 'AzureManagedDomain'

resource emailService 'Microsoft.Communication/emailServices@2023-04-01' = {
  name: emailServiceName
  location: 'global'
  properties: {
    dataLocation: 'United States'
  }
}

resource emailDomain 'Microsoft.Communication/emailServices/domains@2023-04-01' = {
  parent: emailService
  name: domainName
  location: 'global'
  properties: {
    domainManagement: 'AzureManaged'
    userEngagementTracking: 'Disabled'
  }
}

resource communicationService 'Microsoft.Communication/communicationServices@2023-04-01' = {
  name: communicationServiceName
  location: 'global'
  properties: {
    dataLocation: 'United States'
    linkedDomains: [emailDomain.id]
  }
}

output communicationServiceId string = communicationService.id
output communicationServiceName string = communicationService.name
output emailServiceId string = emailService.id
output emailDomainId string = emailDomain.id
output emailDomainName string = emailDomain.properties.mailFromSenderDomain
