"""Query Expansion RAG - HTTP エンドポイント。

提供エンドポイント:
- GET  /api/health        ... 疎通確認
- POST /api/invoke        ... RAG 実行
- GET  /api/ingest-status ... 直近の取り込みレポート（Blob から読み込み）
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from rag.pipeline import RagPipeline

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# -----------------------------------------------------------------------------
# 設定
# -----------------------------------------------------------------------------
APP_VERSION = "0.3.0"

AOAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AOAI_CHAT_DEPLOYMENT = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
AOAI_EMBEDDING_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME", "")
STORAGE_ACCOUNT = os.environ.get("AZURE_STORAGE_ACCOUNT", "")
SOURCE_CONTAINER = os.environ.get("AZURE_STORAGE_SOURCE_CONTAINER", "")
REPORTS_CONTAINER = os.environ.get("AZURE_STORAGE_REPORTS_CONTAINER", "ingest-reports")


def _json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


# -----------------------------------------------------------------------------
# GET /health
# -----------------------------------------------------------------------------
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response(
        {
            "status": "ok",
            "version": APP_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {
                "aoai_endpoint_configured": bool(AOAI_ENDPOINT),
                "aoai_chat_deployment": AOAI_CHAT_DEPLOYMENT,
                "aoai_embedding_deployment": AOAI_EMBEDDING_DEPLOYMENT,
                "search_endpoint_configured": bool(SEARCH_ENDPOINT),
                "search_index_name": SEARCH_INDEX_NAME,
                "storage_account": STORAGE_ACCOUNT,
                "source_container": SOURCE_CONTAINER,
            },
        }
    )


# -----------------------------------------------------------------------------
# POST /invoke
# -----------------------------------------------------------------------------
@app.route(route="invoke", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def invoke(req: func.HttpRequest) -> func.HttpResponse:
    request_id = str(uuid.uuid4())
    logging.info("invoke started: request_id=%s", request_id)

    try:
        body = req.get_json()
    except ValueError:
        return _json_response(
            {"statusCode": 400, "error": "invalid_json", "request_id": request_id},
            status_code=400,
        )

    inputs = body.get("inputs", {}) if isinstance(body, dict) else {}
    input_text = inputs.get("input_text", "") if isinstance(inputs, dict) else ""

    if not input_text:
        return _json_response(
            {
                "statusCode": 400,
                "error": "missing_field",
                "message": "inputs.input_text is required",
                "request_id": request_id,
            },
            status_code=400,
        )

    logging.info("invoke params: request_id=%s, input_text=%r", request_id, input_text[:200])

    try:
        pipeline = RagPipeline.get()
        result = pipeline.invoke(input_text)
    except Exception:  # noqa: BLE001
        # 内部ログには stacktrace を残し、レスポンスからは内部実装情報を隠す
        logging.exception("RAG pipeline failed: request_id=%s", request_id)
        return _json_response(
            {
                "statusCode": 500,
                "error": "internal_error",
                "request_id": request_id,
            },
            status_code=500,
        )

    logging.info("invoke completed: request_id=%s", request_id)
    return _json_response(
        {
            "statusCode": 200,
            "outputs": result.answer,
            "artifacts": [],
            "references": result.references,
            "debug": {"version": APP_VERSION, "request_id": request_id, **result.debug},
        }
    )


# -----------------------------------------------------------------------------
# GET /ingest-status
# Blob 上の latest.json を読んで Markdown で整形して返す
# -----------------------------------------------------------------------------
@app.route(route="ingest-status", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def ingest_status(req: func.HttpRequest) -> func.HttpResponse:
    try:
        account_url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net"
        credential = DefaultAzureCredential()
        client = BlobServiceClient(account_url=account_url, credential=credential)
        blob = client.get_blob_client(container=REPORTS_CONTAINER, blob="latest.json")
        data = json.loads(blob.download_blob().readall().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _json_response(
            {
                "statusCode": 200,
                "outputs": f"## 取り込み状況\n\n_最新レポートを取得できませんでした: {exc}_",
                "debug": {"version": APP_VERSION, "error": str(exc)},
            }
        )

    summary = data.get("summary", {})
    started = data.get("started_at", "-")
    finished = data.get("finished_at", "-")
    failures = data.get("failures", [])
    actions = data.get("actions", [])

    lines = [
        "## 取り込み状況",
        "",
        f"- 実行 ID: `{data.get('run_id', '-')}`",
        f"- 開始: {started}",
        f"- 完了: {finished}",
        "",
        "### 集計",
        f"- 追加: **{summary.get('added', 0)}**",
        f"- 更新: **{summary.get('updated', 0)}**",
        f"- 削除: **{summary.get('deleted', 0)}**",
        f"- 失敗: **{summary.get('failed', 0)}**",
    ]

    if actions:
        lines += ["", "### 実行内容"]
        for a in actions[:20]:
            chunks = a.get("chunks")
            extra = f" ({chunks} chunks)" if chunks else ""
            lines.append(f"- `{a.get('action')}` {a.get('blob_path')}{extra}")
        if len(actions) > 20:
            lines.append(f"- ... ほか {len(actions) - 20} 件")

    if failures:
        lines += ["", "### 失敗詳細"]
        for f in failures[:20]:
            lines.append(
                f"- `{f.get('blob_path', '-')}` : {f.get('error_type', '-')} - {f.get('message', '')}"
            )
        if len(failures) > 20:
            lines.append(f"- ... ほか {len(failures) - 20} 件")

    return _json_response(
        {
            "statusCode": 200,
            "outputs": "\n".join(lines),
            "debug": {"version": APP_VERSION},
        }
    )
