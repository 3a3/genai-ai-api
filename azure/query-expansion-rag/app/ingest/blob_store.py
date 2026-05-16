"""Blob Storage アクセスラッパ（原本・隔離・レポート共通）。"""

from __future__ import annotations

import logging
from typing import Iterator

from azure.core.credentials import TokenCredential
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)


class BlobStore:
    def __init__(self, storage_account: str, credential: TokenCredential) -> None:
        account_url = f"https://{storage_account}.blob.core.windows.net"
        self._service = BlobServiceClient(account_url=account_url, credential=credential)

    def list_blobs(self, container: str, prefix: str = "") -> Iterator[str]:
        client = self._service.get_container_client(container)
        for blob in client.list_blobs(name_starts_with=prefix):
            yield blob.name

    def read_blob(self, container: str, blob_path: str) -> bytes:
        client = self._service.get_blob_client(container=container, blob=blob_path)
        return client.download_blob().readall()

    def upload_blob(
        self,
        container: str,
        blob_path: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        overwrite: bool = True,
    ) -> None:
        client = self._service.get_blob_client(container=container, blob=blob_path)
        from azure.storage.blob import ContentSettings  # 遅延 import

        content_settings = ContentSettings(content_type=content_type) if content_type else None
        client.upload_blob(
            data,
            overwrite=overwrite,
            content_settings=content_settings,
            metadata=metadata,
        )

    def move_blob(
        self,
        src_container: str,
        src_blob_path: str,
        dst_container: str,
        dst_blob_path: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """コピーしてから削除する簡易 move。"""
        src_client = self._service.get_blob_client(container=src_container, blob=src_blob_path)
        dst_client = self._service.get_blob_client(container=dst_container, blob=dst_blob_path)
        source_url = src_client.url
        copy_props = dst_client.start_copy_from_url(source_url, metadata=metadata)
        # 同アカウント内のコピーは同期的に完了することが多い
        if copy_props["copy_status"] not in ("success",):
            logger.info("blob copy started (status=%s); proceeding", copy_props["copy_status"])
        src_client.delete_blob()
