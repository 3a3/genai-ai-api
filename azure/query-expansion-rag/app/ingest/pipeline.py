"""ingest パイプラインのオーケストレーション。"""

from __future__ import annotations

import hashlib
import logging
from typing import Iterable

from azure.core.credentials import TokenCredential

from . import chunkers, loaders, validators
from .blob_store import BlobStore
from .config import IngestConfig
from .embedder import Embedder
from .errors import IngestError
from .quarantine import quarantine_blob
from .report import Report
from .search_client import AISearchClient
from .types import DocType, SourceFile

logger = logging.getLogger(__name__)


def _infer_doc_type(blob_path: str) -> DocType:
    """blob_path のトップディレクトリで判定。

    "qa/..." → qa、それ以外 → rules
    """
    first = blob_path.split("/", 1)[0].lower()
    return "qa" if first == "qa" else "rules"


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class IngestPipeline:
    def __init__(
        self,
        config: IngestConfig,
        credential: TokenCredential,
    ) -> None:
        self.config = config
        self.blob_store = BlobStore(config.storage_account, credential)
        self.embedder = Embedder(
            endpoint=config.aoai_endpoint,
            deployment=config.aoai_embedding_deployment,
            api_version=config.aoai_api_version,
            credential=credential,
            batch_size=config.embedding_batch_size,
            dimensions=config.embedding_dimensions,
        )
        self.search = AISearchClient(
            endpoint=config.search_endpoint,
            index_name=config.search_index_name,
            credential=credential,
            embedding_dim=config.embedding_dimensions,
        )

    def ensure_index(self) -> None:
        self.search.ensure_index()

    # ----- 1 ファイル処理 -----
    def ingest_single(self, blob_path: str, report: Report) -> None:
        try:
            content = self.blob_store.read_blob(self.config.source_container, blob_path)
            mime = validators.validate(blob_path, content, self.config.max_file_size_mb)
            sections = loaders.load(blob_path, content, mime)
            source = SourceFile(
                blob_path=blob_path,
                content=b"",  # ハッシュは取得済みなので破棄
                mime_type=mime,
                doc_type=_infer_doc_type(blob_path),
                source_hash=_sha256_hex(content),
            )
            chunks = chunkers.chunk(source, sections)
            embedded = self.embedder.embed_chunks(chunks)
            # 既存削除 → 新規 upload（mergeOrUpload なら厳密には不要だが chunk 数変動に追従するため delete してから入れる）
            existing = self.search.delete_by_source_path(blob_path)
            self.search.upload_chunks(embedded)
            action = "update" if existing > 0 else "add"
            report.record_success(action, blob_path, chunks=len(embedded), existing_chunks_deleted=existing)
            logger.info("ingested %s: %d chunks (%s)", blob_path, len(embedded), action)
        except IngestError as exc:
            logger.warning("ingest failed for %s: %s", blob_path, exc)
            quarantined = quarantine_blob(
                self.blob_store,
                self.config.source_container,
                self.config.quarantine_container,
                blob_path,
                exc,
                report.run_id,
            )
            report.record_failure(exc, quarantined_to=quarantined or None)

    def delete_single(self, blob_path: str, report: Report) -> None:
        try:
            removed = self.search.delete_by_source_path(blob_path)
            if removed > 0:
                report.record_success("delete", blob_path, removed=removed)
                logger.info("deleted index entries for %s: %d chunks", blob_path, removed)
            else:
                logger.info("no chunks found for %s; skip", blob_path)
        except Exception as exc:  # noqa: BLE001
            from .errors import UploaderError

            err = UploaderError(blob_path, f"delete failed: {exc}")
            report.record_failure(err)

    # ----- ディレクトリ同期 -----
    def sync(self, report: Report, prefix: str = "") -> None:
        """Blob 一覧と AI Search の一覧を突き合わせて差分処理。"""
        blob_paths = set(self.blob_store.list_blobs(self.config.source_container, prefix=prefix))
        indexed_hashes = self.search.list_source_hashes()
        indexed_paths = set(indexed_hashes.keys())

        # 追加または更新
        to_add_or_update = blob_paths
        for path in sorted(to_add_or_update):
            # 既存と hash が同じならスキップ
            content = self.blob_store.read_blob(self.config.source_container, path)
            current_hash = _sha256_hex(content)
            if path in indexed_paths and indexed_hashes[path] == current_hash:
                continue
            # 再ロードが無駄にならないよう、ingest_single を呼び出す代わりに同じフローを使う
            self.ingest_single(path, report)

        # 削除（Blob 側に存在しないが index にある）
        to_delete = indexed_paths - blob_paths
        for path in sorted(to_delete):
            self.delete_single(path, report)
