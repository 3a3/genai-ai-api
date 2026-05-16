"""ingest CLI。

使い方:
  python -m ingest.cli init                     # AI Search インデックス作成
  python -m ingest.cli upload <local_path>      # ローカルファイルを Blob にアップ
  python -m ingest.cli add <blob_path>          # 既に Blob 上にあるファイルを ingest
  python -m ingest.cli delete <blob_path>       # index から削除
  python -m ingest.cli sync [<prefix>]          # Blob と index を同期
  python -m ingest.cli status                   # 最新 report.json を表示
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from azure.identity import DefaultAzureCredential

from .blob_store import BlobStore
from .config import IngestConfig
from .pipeline import IngestPipeline
from .report import Report


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def cmd_init(args: argparse.Namespace) -> int:
    config = IngestConfig.from_env()
    credential = DefaultAzureCredential()
    pipeline = IngestPipeline(config, credential)
    pipeline.ensure_index()
    print(f"OK: index '{config.search_index_name}' is ready")
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    config = IngestConfig.from_env()
    credential = DefaultAzureCredential()
    blob_store = BlobStore(config.storage_account, credential)
    local_path = Path(args.local_path).resolve()
    if not local_path.is_file():
        print(f"ERROR: not a file: {local_path}", file=sys.stderr)
        return 2
    blob_path = args.blob_path or str(local_path.name)
    data = local_path.read_bytes()
    blob_store.upload_blob(config.source_container, blob_path, data, overwrite=True)
    print(f"OK: uploaded -> {config.source_container}/{blob_path} ({len(data)} bytes)")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    config = IngestConfig.from_env()
    credential = DefaultAzureCredential()
    pipeline = IngestPipeline(config, credential)
    pipeline.ensure_index()
    report = Report(_run_id())
    pipeline.ingest_single(args.blob_path, report)
    path = report.save(pipeline.blob_store, config.reports_container)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nreport: {config.reports_container}/{path}")
    return 0 if report.stats.failed == 0 else 1


def cmd_delete(args: argparse.Namespace) -> int:
    config = IngestConfig.from_env()
    credential = DefaultAzureCredential()
    pipeline = IngestPipeline(config, credential)
    report = Report(_run_id())
    pipeline.delete_single(args.blob_path, report)
    path = report.save(pipeline.blob_store, config.reports_container)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nreport: {config.reports_container}/{path}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config = IngestConfig.from_env()
    credential = DefaultAzureCredential()
    pipeline = IngestPipeline(config, credential)
    pipeline.ensure_index()
    report = Report(_run_id())
    pipeline.sync(report, prefix=args.prefix or "")
    path = report.save(pipeline.blob_store, config.reports_container)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nreport: {config.reports_container}/{path}")
    return 0 if report.stats.failed == 0 else 1


def cmd_status(args: argparse.Namespace) -> int:
    config = IngestConfig.from_env()
    credential = DefaultAzureCredential()
    blob_store = BlobStore(config.storage_account, credential)
    try:
        data = blob_store.read_blob(config.reports_container, "latest.json")
        print(data.decode("utf-8"))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"no latest report found: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="ingest", description="RAG ingest pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create AI Search index if not exists")

    p_upload = sub.add_parser("upload", help="Upload a local file to source-docs")
    p_upload.add_argument("local_path", help="local file path")
    p_upload.add_argument("--blob-path", dest="blob_path", default=None, help="target blob path (default: filename)")

    p_add = sub.add_parser("add", help="Ingest a blob into the index")
    p_add.add_argument("blob_path", help="blob path under source-docs/")

    p_del = sub.add_parser("delete", help="Delete a source from the index")
    p_del.add_argument("blob_path", help="blob path under source-docs/")

    p_sync = sub.add_parser("sync", help="Sync source-docs and index")
    p_sync.add_argument("prefix", nargs="?", default="", help="optional blob prefix")

    sub.add_parser("status", help="Show latest ingest report")

    args = parser.parse_args(argv)
    table = {
        "init": cmd_init,
        "upload": cmd_upload,
        "add": cmd_add,
        "delete": cmd_delete,
        "sync": cmd_sync,
        "status": cmd_status,
    }
    return table[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
