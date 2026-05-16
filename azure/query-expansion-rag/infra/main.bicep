// =============================================================================
// Query Expansion RAG on Azure - メインデプロイメント
// =============================================================================
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('環境名（リソースグループおよびリソース名のサフィックスに使用）')
param environmentName string

@minLength(1)
@description('既定リソースのリージョン（AOAI 以外）')
param location string

@description('Azure OpenAI のリージョン（モデル提供リージョンに合わせる）')
param openAiLocation string = 'eastus2'

// ----- Azure OpenAI -----
param openAiChatModelName string = 'gpt-5.4-mini'
param openAiChatModelVersion string = '2026-03-17'
param openAiChatDeploymentSku string = 'GlobalStandard'
param openAiChatDeploymentCapacity int = 50

param openAiEmbeddingModelName string = 'text-embedding-3-small'
param openAiEmbeddingModelVersion string = '1'
param openAiEmbeddingDeploymentSku string = 'Standard'
param openAiEmbeddingDeploymentCapacity int = 50

// ----- AI Search -----
@allowed(['basic', 'standard', 'standard2', 'standard3'])
param searchSku string = 'basic'

// ----- APIM -----
@allowed(['Consumption', 'Developer', 'Basic', 'Standard', 'Premium'])
param apimSku string = 'Consumption'
param apimPublisherEmail string = 'admin@example.com'
param apimPublisherName string = 'Query Expansion RAG'

// ----- API アクセス制限 -----
@description('APIM への接続を許可する送信元 IP の CSV 文字列（例: "192.168.0.1/32,203.0.113.0/24"）。空文字で制限なし。.env で AZURE_API_ALLOWED_SOURCE_IPS にセットして公開リポジトリへの漏洩を防ぐ。')
param apiAllowedSourceIpsCsv string = ''

// CSV を配列化（空文字なら空配列、各要素は trim）
// 注: Bicep は三項演算子内の for-expression を許可しない (BCP138)。先に for-expression を別変数化する。
var apiAllowedSourceIpsTrimmed = [for ip in split(apiAllowedSourceIpsCsv, ','): trim(ip)]
var apiAllowedSourceIps = empty(apiAllowedSourceIpsCsv) ? [] : apiAllowedSourceIpsTrimmed

// ----- 命名 -----
var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
  project: 'query-expansion-rag'
}

// =============================================================================
// リソースグループ
// =============================================================================
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// =============================================================================
// 監視（Log Analytics + Application Insights）
// =============================================================================
module monitoring './core/monitor/monitoring.bicep' = {
  scope: rg
  name: 'monitoring'
  params: {
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
    location: location
    tags: tags
  }
}

// =============================================================================
// Storage（Function 実行用 + 原本格納）
// =============================================================================
module storage './app/storage.bicep' = {
  scope: rg
  name: 'storage'
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
  }
}

// =============================================================================
// Azure OpenAI
// =============================================================================
module openAi './app/openai.bicep' = {
  scope: rg
  name: 'openai'
  params: {
    name: '${abbrs.cognitiveServicesAccounts}aoai-${resourceToken}'
    location: openAiLocation
    tags: tags
    chatModelName: openAiChatModelName
    chatModelVersion: openAiChatModelVersion
    chatDeploymentSku: openAiChatDeploymentSku
    chatDeploymentCapacity: openAiChatDeploymentCapacity
    embeddingModelName: openAiEmbeddingModelName
    embeddingModelVersion: openAiEmbeddingModelVersion
    embeddingDeploymentSku: openAiEmbeddingDeploymentSku
    embeddingDeploymentCapacity: openAiEmbeddingDeploymentCapacity
  }
}

// =============================================================================
// Azure AI Search
// =============================================================================
module aiSearch './app/ai-search.bicep' = {
  scope: rg
  name: 'aisearch'
  params: {
    name: '${abbrs.searchSearchServices}${resourceToken}'
    location: location
    tags: tags
    sku: searchSku
  }
}

// =============================================================================
// Azure Functions (Flex Consumption)
// =============================================================================
module functionApp './app/function.bicep' = {
  scope: rg
  name: 'function'
  params: {
    name: '${abbrs.webSitesFunctions}${resourceToken}'
    planName: '${abbrs.webServerFarms}${resourceToken}'
    location: location
    tags: tags
    storageAccountName: storage.outputs.name
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    openAiEndpoint: openAi.outputs.endpoint
    openAiChatDeployment: openAi.outputs.chatDeploymentName
    openAiEmbeddingDeployment: openAi.outputs.embeddingDeploymentName
    searchEndpoint: aiSearch.outputs.endpoint
    searchIndexName: 'rag-index'
    sourceContainer: storage.outputs.sourceContainerName
  }
}

// =============================================================================
// RBAC: Function MI → AOAI / Search / Storage
// =============================================================================
module rbac './app/rbac.bicep' = {
  scope: rg
  name: 'rbac'
  params: {
    functionPrincipalId: functionApp.outputs.principalId
    openAiAccountName: openAi.outputs.name
    searchServiceName: aiSearch.outputs.name
    storageAccountName: storage.outputs.name
  }
}

// =============================================================================
// APIM + ポリシー
// =============================================================================
module apim './app/apim.bicep' = {
  scope: rg
  name: 'apim'
  params: {
    name: '${abbrs.apiManagementService}${resourceToken}'
    location: location
    tags: tags
    sku: apimSku
    publisherEmail: apimPublisherEmail
    publisherName: apimPublisherName
  }
}

module apimApi './app/apim-api.bicep' = {
  scope: rg
  name: 'apim-api'
  params: {
    apimName: apim.outputs.name
    functionAppName: functionApp.outputs.name
    functionAppHost: functionApp.outputs.defaultHostName
    allowedSourceIps: apiAllowedSourceIps
  }
}

// =============================================================================
// 出力
// =============================================================================
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_OPENAI_ENDPOINT string = openAi.outputs.endpoint
output AZURE_OPENAI_CHAT_DEPLOYMENT string = openAi.outputs.chatDeploymentName
output AZURE_OPENAI_EMBEDDING_DEPLOYMENT string = openAi.outputs.embeddingDeploymentName
output AZURE_SEARCH_ENDPOINT string = aiSearch.outputs.endpoint
output AZURE_SEARCH_INDEX_NAME string = 'rag-index'
output AZURE_STORAGE_ACCOUNT string = storage.outputs.name
output AZURE_STORAGE_SOURCE_CONTAINER string = storage.outputs.sourceContainerName
output FUNCTION_APP_NAME string = functionApp.outputs.name
output FUNCTION_APP_HOST string = functionApp.outputs.defaultHostName
output APIM_SERVICE_NAME string = apim.outputs.name
output APIM_GATEWAY_URL string = apim.outputs.gatewayUrl
output API_ENDPOINT string = '${apim.outputs.gatewayUrl}/rag'
