// Azure Functions (Flex Consumption)
// - Linux / Python 3.11
// - System-Assigned Managed Identity（RBAC で AOAI/Search/Storage に接続）
// - Storage Account へは MI 経由でアクセス（disableLocalAuth=true 対応）
param name string
param planName string
param location string
param tags object = {}

param storageAccountName string
param applicationInsightsConnectionString string

// アプリ設定経由で Function に渡す依存リソース情報
param openAiEndpoint string
param openAiChatDeployment string
param openAiEmbeddingDeployment string
param searchEndpoint string
param searchIndexName string
param sourceContainer string

param runtimeName string = 'python'
param runtimeVersion string = '3.11'
param instanceMemoryMB int = 2048
param maximumInstanceCount int = 40

// デプロイパッケージ格納先（Storage 内のコンテナ）
var deploymentContainerName = 'app-package'

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: storageAccountName
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  tags: tags
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: maximumInstanceCount
        instanceMemoryMB: instanceMemoryMB
      }
      runtime: {
        name: runtimeName
        version: runtimeVersion
      }
    }
    siteConfig: {
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: applicationInsightsConnectionString
        }
        // 業務ロジックが参照する設定
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openAiEndpoint
        }
        {
          name: 'AZURE_OPENAI_CHAT_DEPLOYMENT'
          value: openAiChatDeployment
        }
        {
          name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT'
          value: openAiEmbeddingDeployment
        }
        {
          name: 'AZURE_OPENAI_API_VERSION'
          value: '2024-10-21'
        }
        {
          name: 'AZURE_SEARCH_ENDPOINT'
          value: searchEndpoint
        }
        {
          name: 'AZURE_SEARCH_INDEX_NAME'
          value: searchIndexName
        }
        {
          name: 'AZURE_STORAGE_ACCOUNT'
          value: storage.name
        }
        {
          name: 'AZURE_STORAGE_SOURCE_CONTAINER'
          value: sourceContainer
        }
      ]
    }
  }
}

// Function App の System MI に「自身の Storage コンテナへの Blob Data Owner」権限を付与
// （Flex Consumption はデプロイパッケージを Blob 経由で取得するため必須）
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
resource functionStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, functionApp.id, storageBlobDataOwnerRoleId)
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
  }
}

output name string = functionApp.name
output id string = functionApp.id
output defaultHostName string = functionApp.properties.defaultHostName
output principalId string = functionApp.identity.principalId
