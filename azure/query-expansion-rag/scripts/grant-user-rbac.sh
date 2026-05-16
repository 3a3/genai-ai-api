#!/usr/bin/env bash
# ingest CLI をローカル実行する自分のユーザー (az login したアカウント) に
# 必要なデータプレーン権限を付与する。
#
# 付与するロール:
#   - Storage Blob Data Contributor       (Blob R/W)
#   - Search Index Data Contributor       (索引データ R/W)
#   - Search Service Contributor          (索引スキーマ作成)
#   - Cognitive Services OpenAI User      (AOAI 推論呼び出し)
#
# 一度実行すれば OK（伝播まで 1〜2 分待つ）。

set -eu

RG=$(azd env get-value AZURE_RESOURCE_GROUP)
SUB_ID=$(azd env get-value AZURE_SUBSCRIPTION_ID)
STORAGE_NAME=$(azd env get-value AZURE_STORAGE_ACCOUNT)
SEARCH_NAME=$(basename "$(azd env get-value AZURE_SEARCH_ENDPOINT)" | sed 's/\.search\.windows\.net//')
AOAI_NAME=$(basename "$(azd env get-value AZURE_OPENAI_ENDPOINT)" | sed 's|/$||' | sed 's|^https://||' | cut -d. -f1)

USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)
echo "Granting roles to user object id: $USER_OBJECT_ID"

STORAGE_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Storage/storageAccounts/${STORAGE_NAME}"
SEARCH_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.Search/searchServices/${SEARCH_NAME}"
AOAI_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.CognitiveServices/accounts/${AOAI_NAME}"

assign() {
  local role="$1"
  local scope="$2"
  echo "- $role on ${scope##*/}"
  az role assignment create \
    --assignee-object-id "$USER_OBJECT_ID" \
    --assignee-principal-type User \
    --role "$role" \
    --scope "$scope" >/dev/null 2>&1 \
    || echo "  (already exists or failed; check Portal if errors persist)"
}

assign "Storage Blob Data Contributor" "$STORAGE_SCOPE"
assign "Search Index Data Contributor" "$SEARCH_SCOPE"
assign "Search Service Contributor" "$SEARCH_SCOPE"
assign "Cognitive Services OpenAI User" "$AOAI_SCOPE"

echo
echo "Done. Wait 1-2 minutes for propagation before running ingest."
