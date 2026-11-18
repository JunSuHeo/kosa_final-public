"""Private local evidence checksums, not signatures against same-user forgery."""

import hashlib
import json
import os
from pathlib import Path
import tempfile


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def atomic(directory: Path, name: str, data: bytes):
    if directory.is_symlink() or not directory.is_dir():
        raise OSError("Evidence directory is unavailable")
    descriptor, temporary = tempfile.mkstemp(prefix=".evidence-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        Path(temporary).replace(directory / name)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_json(directory, name, value):
    data = (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode()
    atomic(directory, name, data)
    return hashlib.sha256(data).hexdigest()
