"""検証層: ファイル入力の事前バリデーション。

- マジックバイト判定（拡張子偽装を弾く）
- サイズ上限
- 0 バイト検出
- 対応形式の許可リスト
"""

from __future__ import annotations

from pathlib import Path

from .errors import (
    EmptyFileError,
    FileTooLargeError,
    MimeTypeMismatchError,
    UnsupportedFormatError,
)

# 対応 MIME と対応拡張子のマッピング
SUPPORTED_MIMES: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "text/csv": {".csv"},
    "text/plain": {".txt"},
    "application/json": {".json"},
}


def _sniff_mime(content: bytes) -> str:
    """ファイル先頭バイトから MIME を推定。

    軽量のため magic ライブラリには依存せず、主要形式のみを判定。
    対応外の場合は application/octet-stream を返す。
    """
    if content[:4] == b"%PDF":
        return "application/pdf"
    # ZIP ベース (xlsx / docx / pptx)
    if content[:4] == b"PK\x03\x04":
        # xlsx は内部に [Content_Types].xml + xl/ を含む
        if b"xl/" in content[:8192]:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        # 他のオフィス形式は対応外として扱う（必要なら拡張）
        return "application/zip"
    # JSON (先頭が { or [)
    stripped = content.lstrip(b" \t\r\n")
    if stripped[:1] in (b"{", b"["):
        return "application/json"
    # CSV / TXT: ASCII / UTF-8 で改行ありかを大雑把に判定
    try:
        sample = content[:4096].decode("utf-8")
        if "\n" in sample or "\r" in sample:
            # カンマ区切りが多ければ CSV、そうでなければ txt
            first_line = sample.splitlines()[0] if sample.splitlines() else ""
            if first_line.count(",") >= 1:
                return "text/csv"
            return "text/plain"
    except UnicodeDecodeError:
        pass
    return "application/octet-stream"


def validate(blob_path: str, content: bytes, max_file_size_mb: int = 100) -> str:
    """検証を順に実行。失敗時はそれぞれの例外を送出。

    Returns:
        判定された MIME type
    """
    size = len(content)
    if size == 0:
        raise EmptyFileError(blob_path, "file is empty")

    if size > max_file_size_mb * 1024 * 1024:
        raise FileTooLargeError(
            blob_path,
            f"file size {size} bytes exceeds limit {max_file_size_mb} MB",
            actual_bytes=size,
            limit_mb=max_file_size_mb,
        )

    declared_ext = Path(blob_path).suffix.lower()
    actual_mime = _sniff_mime(content)

    if actual_mime not in SUPPORTED_MIMES:
        raise UnsupportedFormatError(
            blob_path,
            f"unsupported content type: {actual_mime}",
            declared_ext=declared_ext,
            detected_mime=actual_mime,
        )

    allowed_exts = SUPPORTED_MIMES[actual_mime]
    if declared_ext not in allowed_exts:
        raise MimeTypeMismatchError(
            blob_path,
            f"extension {declared_ext} does not match detected content {actual_mime}",
            declared_ext=declared_ext,
            detected_mime=actual_mime,
            expected_exts=sorted(allowed_exts),
        )

    return actual_mime
