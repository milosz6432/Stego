"""Storage layer.

Responsibilities / guarantees:
  * The original uploaded bytes are written once and never modified.
  * Analysis operates on working copies (helpers hand out read-only paths to
    the original; anything that must mutate copies into WORK_DIR first).
  * Extracted/recovered payloads are first-class stored objects that can be
    re-analysed by any module without the user re-uploading.
  * A small JSON sidecar per object makes the registry survive a restart
    within the data dir's lifetime.

Thread-safe for the modest concurrency of a single-user local tool.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from .file_detection import DetectedFormat, detect_file


@dataclass
class StoredFile:
    id: str
    name: str                      # display name (sanitised)
    stored_path: str               # absolute path to the immutable original
    size: int
    sha256: str
    media_type: str
    format: str
    mime: str
    created_at: float
    origin: str = "upload"         # upload | extraction | frame | audio-extract
    parent_id: Optional[str] = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _sanitise(name: str) -> str:
    name = Path(name).name  # strip any path components
    keep = [c for c in name if c.isalnum() or c in " ._-()[]"]
    cleaned = "".join(keep).strip() or "file"
    return cleaned[:200]


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


class Storage:
    def __init__(self) -> None:
        config.ensure_dirs()
        self._lock = threading.RLock()
        self._index: dict[str, StoredFile] = {}
        self._load_existing()

    # ---------------------------------------------------------------- registry
    def _meta_path(self, file_id: str) -> Path:
        return config.UPLOAD_DIR / file_id / "meta.json"

    def _load_existing(self) -> None:
        for meta in config.UPLOAD_DIR.glob("*/meta.json"):
            try:
                data = json.loads(meta.read_text())
                sf = StoredFile(**data)
                if Path(sf.stored_path).exists():
                    self._index[sf.id] = sf
            except Exception:
                continue

    def _persist(self, sf: StoredFile) -> None:
        mp = self._meta_path(sf.id)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(sf.to_dict(), indent=2))

    # ------------------------------------------------------------------ create
    def store_bytes(
        self,
        data: bytes,
        name: str,
        *,
        origin: str = "upload",
        parent_id: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> StoredFile:
        file_id = uuid.uuid4().hex
        d = config.UPLOAD_DIR / file_id
        d.mkdir(parents=True, exist_ok=True)
        safe = _sanitise(name)
        stored = d / f"original_{safe}"
        with open(stored, "wb") as f:
            f.write(data)
        return self._register(file_id, stored, safe, origin, parent_id, meta)

    def store_stream(self, src, name: str, *, origin: str = "upload") -> StoredFile:
        """Store from a file-like object without loading it all into memory."""
        file_id = uuid.uuid4().hex
        d = config.UPLOAD_DIR / file_id
        d.mkdir(parents=True, exist_ok=True)
        safe = _sanitise(name)
        stored = d / f"original_{safe}"
        size = 0
        with open(stored, "wb") as f:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    f.close()
                    shutil.rmtree(d, ignore_errors=True)
                    raise ValueError(
                        f"Upload exceeds limit of {config.MAX_UPLOAD_BYTES} bytes"
                    )
                f.write(chunk)
        return self._register(file_id, stored, safe, origin, None, None)

    def copy_path_in(
        self, src_path: str | Path, name: str, *, origin: str, parent_id: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> StoredFile:
        file_id = uuid.uuid4().hex
        d = config.UPLOAD_DIR / file_id
        d.mkdir(parents=True, exist_ok=True)
        safe = _sanitise(name)
        stored = d / f"original_{safe}"
        shutil.copyfile(src_path, stored)
        return self._register(file_id, stored, safe, origin, parent_id, meta)

    def _register(
        self, file_id: str, stored: Path, name: str, origin: str,
        parent_id: Optional[str], meta: Optional[dict],
    ) -> StoredFile:
        fmt: DetectedFormat = detect_file(stored)
        sf = StoredFile(
            id=file_id,
            name=name,
            stored_path=str(stored),
            size=stored.stat().st_size,
            sha256=sha256_file(stored),
            media_type=fmt.media_type,
            format=fmt.format,
            mime=fmt.mime,
            created_at=time.time(),
            origin=origin,
            parent_id=parent_id,
            meta=meta or {},
        )
        with self._lock:
            self._index[file_id] = sf
            self._persist(sf)
        return sf

    # -------------------------------------------------------------------- read
    def get(self, file_id: str) -> Optional[StoredFile]:
        with self._lock:
            return self._index.get(file_id)

    def require(self, file_id: str) -> StoredFile:
        sf = self.get(file_id)
        if sf is None:
            raise KeyError(f"No such file: {file_id}")
        return sf

    def path(self, file_id: str) -> Path:
        return Path(self.require(file_id).stored_path)

    def list(self) -> list[StoredFile]:
        with self._lock:
            return sorted(self._index.values(), key=lambda s: s.created_at, reverse=True)

    def detected(self, file_id: str) -> DetectedFormat:
        return detect_file(self.require(file_id).stored_path)

    # ----------------------------------------------------------- working copies
    def work_copy(self, file_id: str, suffix: str = "") -> Path:
        """Return a fresh writable copy of the original inside WORK_DIR."""
        src = self.path(file_id)
        dst = config.WORK_DIR / f"{file_id}_{uuid.uuid4().hex[:8]}{suffix or src.suffix}"
        shutil.copyfile(src, dst)
        return dst

    def cache_dir(self, file_id: str) -> Path:
        d = config.CACHE_DIR / file_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------------------------------------------------------- extracted files
    def store_extracted(
        self, data: bytes, name: str, *, parent_id: str, meta: Optional[dict] = None,
    ) -> StoredFile:
        return self.store_bytes(data, name, origin="extraction", parent_id=parent_id, meta=meta)

    def delete(self, file_id: str) -> bool:
        with self._lock:
            sf = self._index.pop(file_id, None)
        if sf is None:
            return False
        shutil.rmtree(config.UPLOAD_DIR / file_id, ignore_errors=True)
        shutil.rmtree(config.CACHE_DIR / file_id, ignore_errors=True)
        return True

    def cleanup_work(self, older_than_seconds: int = 3600) -> int:
        """Remove stale scratch working copies."""
        now = time.time()
        removed = 0
        for p in config.WORK_DIR.glob("*"):
            try:
                if now - p.stat().st_mtime > older_than_seconds:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
        return removed


# Module-level singleton
storage = Storage()
