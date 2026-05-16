// API Management
// - 既定は Consumption（従量・初期コスト ¥0）
// - System-Assigned Managed Identity を有効化（将来 AOAI へ直接ルーティングする場合に備えて）
param name string
param location string
param tags object = {}

@allowed(['Consumption', 'Developer', 'Basic', 'Standard', 'Premium'])
param sku string = 'Consumption'

param publisherEmail string
param publisherName string

// Consumption 以外では capacity > 0、Consumption では 0
var capacity = sku == 'Consumption' ? 0 : 1

resource apim 'Microsoft.ApiManagement/service@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    capacity: capacity
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
    publicNetworkAccess: 'Enabled'
  }
}

output name string = apim.name
output id string = apim.id
output gatewayUrl string = apim.properties.gatewayUrl
output principalId string = apim.identity.principalId
