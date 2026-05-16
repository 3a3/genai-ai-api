// Azure OpenAI アカウント + 2 つのデプロイ
// - Chat:      gpt-5.4-mini (Global Standard)
// - Embedding: text-embedding-3-small
param name string
param location string
param tags object = {}

// Chat モデル
param chatModelName string
param chatModelVersion string
param chatDeploymentSku string = 'GlobalStandard'
param chatDeploymentCapacity int = 50

// Embedding モデル
param embeddingModelName string
param embeddingModelVersion string
param embeddingDeploymentSku string = 'Standard'
param embeddingDeploymentCapacity int = 50

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: chatModelName
  sku: {
    name: chatDeploymentSku
    capacity: chatDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: chatModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: embeddingModelName
  sku: {
    name: embeddingDeploymentSku
    capacity: embeddingDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
  // モデルデプロイは順次作成（同じ親に同時作成すると稀に競合する）
  dependsOn: [
    chatDeployment
  ]
}

output name string = account.name
output id string = account.id
output endpoint string = account.properties.endpoint
output chatDeploymentName string = chatDeployment.name
output embeddingDeploymentName string = embeddingDeployment.name
