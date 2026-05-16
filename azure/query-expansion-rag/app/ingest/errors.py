"""ingest パイプラインの例外型。

設計方針:
- IngestError を基底とし、ステージ・原因がトレースしやすい属性を持たせる
- 例外は捕捉時に Quarantine 判定とレポート生成に使う
"""

from __future__ import annotations

from typing import Any


class IngestError(Exception):
    """ingest パイプラインの基底例外。"""

    stage: str = "unknown"

    def __init__(self, blob_path: str, message: str = "", **extra: Any) -> None:
        self.blob_path = blob_path
        self.message = message
        self.extra = extra
        super().__init__(f"[{self.__class__.__name__}] {blob_path}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "stage": self.stage,
            "blob_path": self.blob_path,
            "message": self.message,
            **self.extra,
        }


# ----- Validator stage -----
class ValidationError(IngestError):
    stage = "validator"


class EmptyFileError(ValidationError):
    pass


class FileTooLargeError(ValidationError):
    pass


class UnsupportedFormatError(ValidationError):
    pass


class MimeTypeMismatchError(ValidationError):
    pass


# ----- Loader stage -----
class LoaderError(IngestError):
    stage = "loader"


class PasswordProtectedError(LoaderError):
    pass


class CorruptedFileError(LoaderError):
    pass


class NoTextExtractedError(LoaderError):
    pass


# ----- Chunker stage -----
class ChunkerError(IngestError):
    stage = "chunker"


# ----- Embedder stage -----
class EmbedderError(IngestError):
    stage = "embedder"


# ----- Uploader stage -----
class UploaderError(IngestError):
    stage = "uploader"
