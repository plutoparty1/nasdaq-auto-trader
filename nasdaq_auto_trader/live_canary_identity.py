from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Protocol


class _Digest(Protocol):
    def update(self, value: bytes) -> None: ...


def account_fingerprint(account_number: str, product_code: str) -> str:
    canonical = f"kis-real|{account_number}|{product_code}".encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def executable_sha256(executable: Path) -> str:
    digest = hashlib.sha256()
    if executable.is_dir():
        for source_path in sorted(executable.rglob("*.py")):
            relative = source_path.relative_to(executable).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            _update_digest(digest, source_path)
        return digest.hexdigest()
    _update_digest(digest, executable)
    return digest.hexdigest()


def runtime_identity_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve().parent


def _update_digest(digest: _Digest, source_path: Path) -> None:
    with source_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
