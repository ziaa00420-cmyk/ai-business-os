"""File storage behind a small interface.

Local disk for development and tests. The plan's S3-compatible bucket in the
EU region slots in as another implementation of the same two methods.
"""

from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.config import get_settings


class Storage(Protocol):
    def put(self, business_id: UUID, filename: str, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def put(self, business_id: UUID, filename: str, data: bytes) -> str:
        suffix = Path(filename).suffix.lower()[:10]
        key = f"{business_id}/{uuid4()}{suffix}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("invalid storage key")
        return path.read_bytes()


def get_storage() -> Storage:
    return LocalStorage(get_settings().storage_dir)
