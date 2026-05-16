// Azure AI Search
// - Basic SKU（1 パーティション、最大 3 レプリカ、15 GB）
// - ローカル認証無効化（MI による RBAC のみ）
// - インデックススキーマは ingest スクリプトから REST API で作成（Bicep では作らない）
param name string
param location string
param tags object = {}

@allowed(['basic', 'standard', 'standard2', 'standard3'])
param sku string = 'basic'

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    disableLocalAuth: true
    // 'free' = 月 1000 クエリまで無料、'standard' = 従量課金。MVP は free で開始。
    semanticSearch: 'free'
    authOptions: null
  }
  identity: {
    type: 'SystemAssigned'
  }
}

output name string = searchService.name
output id string = searchService.id
output endpoint string = 'https://${searchService.name}.search.windows.net'
