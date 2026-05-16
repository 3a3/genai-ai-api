// Storage Account
// - Function App の実行用バックエンド
// - RAG 原本ファイル格納（source-docs コンテナ）
// - 取り込み結果レポート格納（ingest-reports コンテナ）
// - 失敗ファイル隔離（quarantine コンテナ）
param name string
param location string
param tags object = {}

// Function App が直接アクセスするための Flex Consumption デプロイ用コンテナ
var deploymentContainerName = 'app-package'
var sourceContainerName = 'source-docs'
var quarantineContainerName = 'quarantine'
var reportsContainerName = 'ingest-reports'

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }

  resource blobService 'blobServices' = {
    name: 'default'
    properties: {
      deleteRetentionPolicy: {
        enabled: true
        days: 30
      }
      containerDeleteRetentionPolicy: {
        enabled: true
        days: 30
      }
      isVersioningEnabled: true
    }
    resource deploymentContainer 'containers' = {
      name: deploymentContainerName
      properties: {
        publicAccess: 'None'
      }
    }
    resource sourceContainer 'containers' = {
      name: sourceContainerName
      properties: {
        publicAccess: 'None'
      }
    }
    resource quarantineContainer 'containers' = {
      name: quarantineContainerName
      properties: {
        publicAccess: 'None'
      }
    }
    resource reportsContainer 'containers' = {
      name: reportsContainerName
      properties: {
        publicAccess: 'None'
      }
    }
  }
}

output name string = storage.name
output id string = storage.id
output primaryBlobEndpoint string = storage.properties.primaryEndpoints.blob
output deploymentContainerName string = deploymentContainerName
output sourceContainerName string = sourceContainerName
output quarantineContainerName string = quarantineContainerName
output reportsContainerName string = reportsContainerName
