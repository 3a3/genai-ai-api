"""ローダー層: MIME に応じたパーサ振り分け。"""

from __future__ import annotations

from ..errors import UnsupportedFormatError
from ..types import Section
from . import excel as excel_loader
from . import pdf as pdf_loader


def load(blob_path: str, content: bytes, mime_type: str) -> list[Section]:
    """MIME ごとのローダーへディスパッチ。"""
    if mime_type == "application/pdf":
        return pdf_loader.load_pdf(blob_path, content)
    if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return excel_loader.load_xlsx(blob_path, content)
    raise UnsupportedFormatError(blob_path, f"no loader for MIME: {mime_type}")
