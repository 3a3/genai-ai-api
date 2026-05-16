// APIM 上に RAG API を定義し、Function を backend として登録
// - パス: /rag/*
// - 認証: subscription key (x-api-key ヘッダ)
// - IP 制限: allowedSourceIps が非空ならポリシーで制限
param apimName string
param functionAppName string
param functionAppHost string

@description('APIM への接続を許可する送信元 IP（CIDR）。空配列で制限なし。')
param allowedSourceIps array = []

resource apim 'Microsoft.ApiManagement/service@2024-06-01-preview' existing = {
  name: apimName
}

// Named Value: Function のデフォルトキー（postprovision フックで更新）
resource functionKeyNamedValue 'Microsoft.ApiManagement/service/namedValues@2024-06-01-preview' = {
  parent: apim
  name: 'function-app-key'
  properties: {
    displayName: 'function-app-key'
    secret: true
    value: 'placeholder-set-by-postprovision-hook'
  }
}

// Named Value: 許可 IP リスト（運用ポリシーで参照、MVP では未使用）
// APIM は空文字を許可しないため、未設定時は 'none' プレースホルダを入れる
resource allowedIpsNamedValue 'Microsoft.ApiManagement/service/namedValues@2024-06-01-preview' = {
  parent: apim
  name: 'allowed-source-ips'
  properties: {
    displayName: 'allowed-source-ips'
    secret: false
    value: empty(allowedSourceIps) ? 'none' : join(allowedSourceIps, ',')
  }
}

// Named Value: Backend ID（ポリシー XML から参照）
resource backendIdNamedValue 'Microsoft.ApiManagement/service/namedValues@2024-06-01-preview' = {
  parent: apim
  name: 'function-backend-id'
  properties: {
    displayName: 'function-backend-id'
    secret: false
    value: functionAppName
  }
}

// Backend: Function App
resource backend 'Microsoft.ApiManagement/service/backends@2024-06-01-preview' = {
  parent: apim
  name: functionAppName
  properties: {
    description: 'Query Expansion RAG Function App'
    url: 'https://${functionAppHost}/api'
    protocol: 'http'
    credentials: {
      header: {
        'x-functions-key': [
          '{{function-app-key}}'
        ]
      }
    }
  }
  dependsOn: [
    functionKeyNamedValue
  ]
}

// Product: GenAI Product（subscription key 必須）
resource product 'Microsoft.ApiManagement/service/products@2024-06-01-preview' = {
  parent: apim
  name: 'genai-product'
  properties: {
    displayName: 'GenAI Product'
    description: 'Query Expansion RAG access'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
  }
}

// API
resource ragApi 'Microsoft.ApiManagement/service/apis@2024-06-01-preview' = {
  parent: apim
  name: 'rag'
  properties: {
    displayName: 'Query Expansion RAG'
    path: 'rag'
    protocols: ['https']
    subscriptionRequired: true
    subscriptionKeyParameterNames: {
      header: 'x-api-key'
      query: 'api-key'
    }
  }
}

// API <-> Product 関連付け
resource productApi 'Microsoft.ApiManagement/service/products/apiLinks@2024-06-01-preview' = {
  parent: product
  name: 'rag'
  properties: {
    apiId: ragApi.id
  }
}

// オペレーション: GET /health
resource healthOp 'Microsoft.ApiManagement/service/apis/operations@2024-06-01-preview' = {
  parent: ragApi
  name: 'health'
  properties: {
    displayName: 'Health Check'
    method: 'GET'
    urlTemplate: '/health'
  }
}

// オペレーション: POST /invoke
resource invokeOp 'Microsoft.ApiManagement/service/apis/operations@2024-06-01-preview' = {
  parent: ragApi
  name: 'invoke'
  properties: {
    displayName: 'Invoke RAG'
    method: 'POST'
    urlTemplate: '/invoke'
  }
}

// オペレーション: GET /ingest-status
resource ingestStatusOp 'Microsoft.ApiManagement/service/apis/operations@2024-06-01-preview' = {
  parent: ragApi
  name: 'ingest-status'
  properties: {
    displayName: 'Ingest Status'
    method: 'GET'
    urlTemplate: '/ingest-status'
  }
}

// IP allowlist 用 XML スニペット生成
// APIM の <ip-filter>/<address> は単一 IP のみサポート（CIDR 非対応）のため、/32 等のプレフィックスを除去
var ipAddressesOnly = [for ip in allowedSourceIps: split(ip, '/')[0]]
var ipFilterAddressesXml = empty(ipAddressesOnly) ? '' : '<address>${join(ipAddressesOnly, '</address><address>')}</address>'
var ipFilterSnippet = empty(ipAddressesOnly) ? '' : '<ip-filter action="allow">${ipFilterAddressesXml}</ip-filter>'
var apiPolicyValue = replace(loadTextContent('./apim-api-policy.xml'), '<!--IP_FILTER_PLACEHOLDER-->', ipFilterSnippet)

// API レベルポリシー（全オペレーションに適用）
resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-06-01-preview' = {
  parent: ragApi
  name: 'policy'
  properties: {
    value: apiPolicyValue
    format: 'xml'
  }
  dependsOn: [
    backend
    allowedIpsNamedValue
    backendIdNamedValue
  ]
}
