"""PDF ローダー。

- pypdf でテキスト抽出
- パスワード保護を検出して PasswordProtectedError
- テキストが取れない（スキャン PDF 等）は NoTextExtractedError
- ページごとに 1 Section を作る（章節分割は chunker に任せる）
"""

from __future__ import annotations

import io

from ..errors import CorruptedFileError, NoTextExtractedError, PasswordProtectedError
from ..types import Section


def load_pdf(blob_path: str, content: bytes) -> list[Section]:
    try:
        import pypdf  # 遅延 import（ingest 専用依存）
    except ImportError as exc:  # pragma: no cover
        raise CorruptedFileError(blob_path, f"pypdf is not installed: {exc}") from exc

    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001 - pypdf 内部例外を広く拾う
        raise CorruptedFileError(blob_path, f"failed to open PDF: {exc}") from exc

    if reader.is_encrypted:
        # 空パスワードで開けるか試す
        try:
            if reader.decrypt("") == 0:
                raise PasswordProtectedError(blob_path, "PDF is password protected")
        except PasswordProtectedError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PasswordProtectedError(
                blob_path, f"PDF is encrypted and could not be opened: {exc}"
            ) from exc

    if len(reader.pages) == 0:
        raise CorruptedFileError(blob_path, "PDF has zero pages")

    sections: list[Section] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - 一部ページだけ壊れていることがある
            text = ""
        text = text.strip()
        if not text:
            continue
        sections.append(
            Section(
                text=text,
                title="",
                section="",
                page=page_idx,
                locator=f"page={page_idx}",
            )
        )

    if not sections:
        raise NoTextExtractedError(
            blob_path,
            "no text extracted from PDF (possibly scanned image; OCR required)",
        )

    return sections
