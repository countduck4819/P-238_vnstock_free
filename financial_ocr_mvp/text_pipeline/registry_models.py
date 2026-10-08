from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

NAMESPACE = uuid.UUID("c5dbe3c4-cfd6-4a5f-8d45-7e894f8e2d7d")


def document_id(path: str) -> str:
    return str(uuid.uuid5(NAMESPACE, path.replace("\\", "/")))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
