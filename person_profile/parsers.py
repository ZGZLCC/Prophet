"""Read supported upload formats into normalized text without storing files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path

from . import storage


SUPPORTED_EXTENSIONS = ("txt", "md", "csv", "json", "pdf", "docx", "xlsx")
TEXT_ENCODINGS = ("gb18030", "big5", "utf-16", "latin-1")
DEFAULT_MAX_FILE_MB = 20
DEFAULT_MAX_TEXT_CHARS = 200_000
DEFAULT_MAX_TABLE_ROWS = 10_000

MIME_TYPES = {
    "txt": {"text/plain", "application/octet-stream", "binary/octet-stream"},
    "md": {
        "text/markdown",
        "text/plain",
        "application/octet-stream",
        "binary/octet-stream",
    },
    "csv": {
        "text/csv",
        "application/csv",
        "text/plain",
        "application/octet-stream",
        "binary/octet-stream",
    },
    "json": {
        "application/json",
        "text/json",
        "text/plain",
        "application/octet-stream",
        "binary/octet-stream",
    },
    "pdf": {"application/pdf", "application/octet-stream", "binary/octet-stream"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/octet-stream",
        "binary/octet-stream",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "binary/octet-stream",
    },
}


class ParserError(ValueError):
    """Base class for upload validation and extraction failures."""


class UnsupportedFileError(ParserError):
    pass


class FileTooLargeError(ParserError):
    pass


class EncodingRequiredError(ParserError):
    def __init__(self, filename: str):
        self.filename = filename
        super().__init__(f"{filename} 不是 UTF-8，请选择文件编码后重试")


class EmptyContentError(ParserError):
    pass


class TextTooLongError(ParserError):
    pass


@dataclass(frozen=True)
class ParsedFile:
    name: str
    extension: str
    mime_type: str
    text: str


def _positive_env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def max_file_bytes() -> int:
    return _positive_env_int("MAX_FILE_MB", DEFAULT_MAX_FILE_MB) * 1024 * 1024


def max_text_chars() -> int:
    return _positive_env_int("MAX_TEXT_CHARS", DEFAULT_MAX_TEXT_CHARS)


def max_table_rows() -> int:
    return _positive_env_int("MAX_TABLE_ROWS", DEFAULT_MAX_TABLE_ROWS)


def _file_info(filename: str) -> tuple[str, str]:
    if not isinstance(filename, str) or not filename.strip():
        raise UnsupportedFileError("文件名为空")
    display_name = Path(filename).name
    extension = Path(display_name).suffix.lower().lstrip(".")
    if extension not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(f".{item}" for item in SUPPORTED_EXTENSIONS)
        raise UnsupportedFileError(f"不支持 {display_name}，仅支持：{allowed}")
    return display_name, extension


def _check_mime(extension: str, mime_type: str | None) -> str:
    normalized = (mime_type or "").split(";", 1)[0].strip().lower()
    if normalized and normalized not in MIME_TYPES[extension]:
        raise UnsupportedFileError(
            f"文件类型与扩展名不匹配：.{extension} / {normalized}"
        )
    return normalized


def _decode_text(data: bytes, filename: str, encoding: str | None) -> str:
    selected_encoding = encoding or "utf-8-sig"
    try:
        return data.decode(selected_encoding)
    except (LookupError, UnicodeDecodeError) as error:
        if encoding is None:
            raise EncodingRequiredError(filename) from error
        raise ParserError(f"无法用 {encoding} 解码 {filename}") from error


def _parse_text(data: bytes, filename: str, encoding: str | None) -> str:
    return _decode_text(data, filename, encoding)


def _parse_csv(data: bytes, filename: str, encoding: str | None) -> str:
    text = _decode_text(data, filename, encoding)
    try:
        reader = csv.reader(io.StringIO(text), strict=True)
        rows = []
        truncated = False
        for index, row in enumerate(reader):
            if index >= max_table_rows():
                truncated = True
                break
            cells = [cell.strip() for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
    except csv.Error as error:
        raise ParserError(f"CSV 文件损坏或格式非法：{filename}") from error
    if truncated:
        rows.append(f"[表格已截断：最多读取 {max_table_rows()} 行]")
    return "\n".join(rows)


def _parse_json(data: bytes, filename: str, encoding: str | None) -> str:
    text = _decode_text(data, filename, encoding)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ParserError(f"JSON 文件格式非法：{filename}") from error
    return json.dumps(value, ensure_ascii=False, indent=2)


def _parse_pdf(data: bytes, filename: str) -> str:
    if b"%PDF-" not in data[:1024]:
        raise ParserError(f"PDF 文件损坏或格式非法：{filename}")
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise ParserError(f"PDF 已加密，无法读取：{filename}")
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[第 {index} 页]\n{text}")
        return "\n\n".join(pages)
    except ParserError:
        raise
    except Exception as error:
        raise ParserError(f"PDF 文件损坏或无法提取文字：{filename}") from error


def _parse_docx(data: bytes, filename: str) -> str:
    try:
        from docx import Document

        document = Document(io.BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table_index, table in enumerate(document.tables, start=1):
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                parts.append(f"[表格 {table_index}]\n" + "\n".join(rows))
        return "\n\n".join(parts)
    except Exception as error:
        raise ParserError(f"DOCX 文件损坏或无法提取文字：{filename}") from error


def _parse_xlsx(data: bytes, filename: str) -> str:
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(
            io.BytesIO(data), read_only=True, data_only=True
        )
        parts = []
        truncated = False
        try:
            for worksheet in workbook.worksheets:
                rows = []
                for index, row in enumerate(
                    worksheet.iter_rows(values_only=True), start=1
                ):
                    if index > max_table_rows():
                        truncated = True
                        break
                    cells = ["" if value is None else str(value).strip() for value in row]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if rows:
                    parts.append(f"[工作表 {worksheet.title}]\n" + "\n".join(rows))
        finally:
            workbook.close()
        if truncated:
            parts.append(f"[表格已截断：每个工作表最多读取 {max_table_rows()} 行]")
        return "\n\n".join(parts)
    except Exception as error:
        raise ParserError(f"XLSX 文件损坏或无法读取：{filename}") from error


def parse_file(
    filename: str,
    data: bytes,
    *,
    mime_type: str | None = None,
    encoding: str | None = None,
    max_bytes: int | None = None,
    max_chars: int | None = None,
) -> ParsedFile:
    """Parse bytes from an upload; never writes the original file to disk."""

    display_name, extension = _file_info(filename)
    normalized_mime = _check_mime(extension, mime_type)
    payload = bytes(data)
    limit = max_file_bytes() if max_bytes is None else max_bytes
    if len(payload) > limit:
        raise FileTooLargeError(
            f"{display_name} 超过大小限制（上限 {limit / 1024 / 1024:.0f} MB）"
        )

    if extension in {"txt", "md"}:
        text = _parse_text(payload, display_name, encoding)
    elif extension == "csv":
        text = _parse_csv(payload, display_name, encoding)
    elif extension == "json":
        text = _parse_json(payload, display_name, encoding)
    elif extension == "pdf":
        text = _parse_pdf(payload, display_name)
    elif extension == "docx":
        text = _parse_docx(payload, display_name)
    else:
        text = _parse_xlsx(payload, display_name)

    normalized_text = storage.normalize_text(text)
    if not normalized_text:
        if extension == "pdf":
            raise EmptyContentError(f"{display_name} 未提取到文字，可能是扫描版 PDF")
        raise EmptyContentError(f"{display_name} 不包含可用文字")
    char_limit = max_text_chars() if max_chars is None else max_chars
    if len(normalized_text) > char_limit:
        raise TextTooLongError(
            f"{display_name} 提取出 {len(normalized_text)} 个字符，超过上限 {char_limit}"
        )
    return ParsedFile(display_name, extension, normalized_mime, normalized_text)


def parse_uploaded_file(
    uploaded_file,
    *,
    encoding: str | None = None,
    max_bytes: int | None = None,
    max_chars: int | None = None,
) -> ParsedFile:
    filename = getattr(uploaded_file, "name", "")
    mime_type = getattr(uploaded_file, "type", None)
    if hasattr(uploaded_file, "getvalue"):
        data = uploaded_file.getvalue()
    else:
        data = uploaded_file.read()
    return parse_file(
        filename,
        data,
        mime_type=mime_type,
        encoding=encoding,
        max_bytes=max_bytes,
        max_chars=max_chars,
    )
