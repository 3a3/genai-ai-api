"""ingest 実行レポートを Blob に保存。

形式は ingest-reports/<run_id>.json
最新を /ingest-status から取得しやすいよう、latest.json も上書きする。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .blob_store import BlobStore
from .errors import IngestError
from .types import IngestStats

logger = logging.getLogger(__name__)


class Report:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.stats = IngestStats()
        self.failures: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []  # add/update/delete のログ

    def record_success(self, action: str, blob_path: str, **extra: Any) -> None:
        self.actions.append(
            {"action": action, "blob_path": blob_path, **extra}
        )
        if action == "add":
            self.stats.added += 1
        elif action == "update":
            self.stats.updated += 1
        elif action == "delete":
            self.stats.deleted += 1

    def record_failure(self, error: IngestError, quarantined_to: str | None = None) -> None:
        item = error.to_dict()
        if quarantined_to:
            item["quarantined_to"] = quarantined_to
        self.failures.append(item)
        self.stats.failed += 1

    def to_dict(self) -> dict[str, Any]:
        self.stats.total = self.stats.added + self.stats.updated + self.stats.deleted + self.stats.failed
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "summary": asdict(self.stats),
            "actions": self.actions,
            "failures": self.failures,
        }

    def save(self, blob_store: BlobStore, container: str) -> str:
        data = json.dumps(self.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        path = f"{self.run_id}.json"
        blob_store.upload_blob(container, path, data, content_type="application/json")
        blob_store.upload_blob(container, "latest.json", data, content_type="application/json")
        logger.info("report saved to %s/%s", container, path)
        return path
