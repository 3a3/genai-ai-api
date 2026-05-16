"""失敗ファイルの隔離。

source-docs から quarantine コンテナへ Blob を移動し、エラー情報を metadata に記録する。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .blob_store import BlobStore
from .errors import IngestError

logger = logging.getLogger(__name__)


def quarantine_blob(
    blob_store: BlobStore,
    source_container: str,
    quarantine_container: str,
    blob_path: str,
    error: IngestError,
    run_id: str,
) -> str:
    """失敗 Blob を quarantine/<run_id>/<元パス> に移動。"""
    dst = f"{run_id}/{blob_path}"
    metadata = {
        "error_type": error.__class__.__name__,
        "error_message": error.message[:1024],
        "error_stage": error.stage,
        "original_path": blob_path,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
    }
    # 安全のため文字列正規化（Azure metadata は ASCII プリンタブル制限あり）
    metadata = {k: _ascii_safe(v) for k, v in metadata.items()}
    try:
        blob_store.move_blob(
            src_container=source_container,
            src_blob_path=blob_path,
            dst_container=quarantine_container,
            dst_blob_path=dst,
            metadata=metadata,
        )
        logger.info("quarantined %s -> %s/%s", blob_path, quarantine_container, dst)
        return f"{quarantine_container}/{dst}"
    except Exception as exc:  # noqa: BLE001
        logger.error("failed to quarantine %s: %s", blob_path, exc)
        return ""


def _ascii_safe(value: str) -> str:
    return value.encode("ascii", errors="replace").decode("ascii")
