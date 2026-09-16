from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, is_zipfile

from docx import Document
from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.exceptions import AppError

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_TYPES = {
    ".pdf": ("pdf", PDF_MIME),
    ".docx": ("docx", DOCX_MIME),
}
READ_CHUNK_SIZE = 1024 * 1024
MAX_DOCX_ENTRIES = 500
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class ValidatedUpload:
    content: bytes
    original_name: str
    file_format: str
    mime_type: str
    sha256: str

    @property
    def size_bytes(self) -> int:
        return len(self.content)


async def read_upload_limited(upload: UploadFile, max_size_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(READ_CHUNK_SIZE):
        total += len(chunk)
        if total > max_size_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"文件大小不能超过 {max_size_bytes // (1024 * 1024)}MB",
                413,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def sanitize_original_filename(filename: str | None) -> str:
    if not filename:
        raise AppError("INVALID_FILENAME", "文件名不能为空", 400)
    basename = Path(filename.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKC", basename)
    safe_name = re.sub(r"[^\w.\- ()\u4e00-\u9fff]", "_", normalized).strip(" .")
    if not safe_name:
        raise AppError("INVALID_FILENAME", "文件名无效", 400)
    return safe_name[:200]


def validate_resume_upload(
    filename: str | None,
    content_type: str | None,
    content: bytes,
    max_size_bytes: int,
) -> ValidatedUpload:
    safe_name = sanitize_original_filename(filename)
    if not content:
        raise AppError("EMPTY_FILE", "不能上传空文件", 400)
    if len(content) > max_size_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"文件大小不能超过 {max_size_bytes // (1024 * 1024)}MB",
            413,
        )

    extension = Path(safe_name).suffix.casefold()
    expected = ALLOWED_TYPES.get(extension)
    if expected is None:
        raise AppError("UNSUPPORTED_FILE_TYPE", "仅支持 PDF 或 DOCX 简历", 415)
    file_format, expected_mime = expected
    normalized_mime = (content_type or "").split(";", maxsplit=1)[0].strip().casefold()
    if normalized_mime != expected_mime:
        raise AppError("MIME_TYPE_MISMATCH", "文件 MIME 类型与扩展名不一致", 415)

    if file_format == "pdf":
        _validate_pdf(content)
    else:
        _validate_docx(content)

    return ValidatedUpload(
        content=content,
        original_name=safe_name,
        file_format=file_format,
        mime_type=expected_mime,
        sha256=sha256(content).hexdigest(),
    )


def _validate_pdf(content: bytes) -> None:
    if not content.startswith(b"%PDF-"):
        raise AppError("FILE_SIGNATURE_MISMATCH", "文件内容不是有效 PDF", 415)
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise AppError("ENCRYPTED_FILE_UNSUPPORTED", "暂不支持加密 PDF", 422)
        if not reader.pages:
            raise AppError("DAMAGED_FILE", "PDF 不包含可读取页面", 400)
    except AppError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise AppError("DAMAGED_FILE", "PDF 文件损坏或结构无效", 400) from exc


def _validate_docx(content: bytes) -> None:
    buffer = BytesIO(content)
    if not content.startswith(b"PK") or not is_zipfile(buffer):
        raise AppError("FILE_SIGNATURE_MISMATCH", "文件内容不是有效 DOCX", 415)
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise AppError("DAMAGED_FILE", "DOCX 缺少必要文档结构", 400)
            if len(names) > MAX_DOCX_ENTRIES:
                raise AppError("UNSAFE_ARCHIVE", "DOCX 内部文件数量异常", 400)
            total_uncompressed = 0
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise AppError("UNSAFE_ARCHIVE", "DOCX 包含不安全路径", 400)
                if item.flag_bits & 0x1:
                    raise AppError("ENCRYPTED_FILE_UNSUPPORTED", "暂不支持加密 DOCX", 422)
                total_uncompressed += item.file_size
            if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise AppError("UNSAFE_ARCHIVE", "DOCX 解压后体积异常", 400)
        Document(BytesIO(content))
    except AppError:
        raise
    except (BadZipFile, KeyError, OSError, ValueError) as exc:
        raise AppError("DAMAGED_FILE", "DOCX 文件损坏或结构无效", 400) from exc
