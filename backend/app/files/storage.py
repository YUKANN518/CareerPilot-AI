from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.exceptions import AppError


class PrivateFileStorage:
    def __init__(self, root_directory: str) -> None:
        self.root = Path(root_directory).resolve()

    def save(self, owner_id: int, file_format: str, content: bytes) -> str:
        storage_key = f"{owner_id}/{uuid4().hex}.{file_format}"
        target = self._safe_path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        return storage_key

    def resolve_existing(self, storage_key: str) -> Path:
        target = self._safe_path(storage_key)
        if not target.is_file():
            raise AppError("FILE_NOT_FOUND", "简历原始文件不存在", 404)
        return target

    def exists(self, storage_key: str) -> bool:
        return self._safe_path(storage_key).is_file()

    def delete(self, storage_key: str) -> None:
        target = self._safe_path(storage_key)
        if target.exists():
            target.unlink()
        parent = target.parent
        if parent != self.root and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

    def _safe_path(self, storage_key: str) -> Path:
        target = (self.root / storage_key).resolve()
        if not target.is_relative_to(self.root):
            raise AppError("UNSAFE_STORAGE_KEY", "文件存储键无效", 400)
        return target
