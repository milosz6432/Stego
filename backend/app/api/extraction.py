"""Payload extraction API: signature scan, carving, trailing data, archive
handling, and recursive analysis of recovered payloads."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.storage import storage
from ..core.util import b64, hex_dump, find_interesting, find_text_strings
from ..extraction import payload as payload_mod
from ..extraction import signatures

router = APIRouter(prefix="/api/extraction", tags=["extraction"])


def _require(file_id: str):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    return sf


@router.get("/analyse/{file_id}")
def analyse(file_id: str):
    """Signature scan + carve + interesting-text over the whole file."""
    sf = _require(file_id)
    data = Path(sf.stored_path).read_bytes()
    result = payload_mod.analyse_blob(data)
    result.pop("carved_data", None)   # don't ship raw bytes here
    return result


@router.get("/signatures/{file_id}")
def scan_signatures(file_id: str):
    sf = _require(file_id)
    data = Path(sf.stored_path).read_bytes()
    return {"signatures": signatures.scan(data, max_results=500)}


@router.get("/trailing/{file_id}")
def trailing(file_id: str):
    sf = _require(file_id)
    tr = payload_mod.trailing_data(sf.stored_path, sf.format)
    if not tr:
        return {"has_trailing": False}
    return {
        "has_trailing": True,
        "size": tr["size"],
        "printable_ratio": tr["printable_ratio"],
        "signatures": tr["signatures"],
        "hex": hex_dump(tr["data"][:512]),
        "preview": tr["data"][:256].decode("latin-1", "replace"),
    }


class CarveRequest(BaseModel):
    file_id: str
    offset: int
    size: int
    name: Optional[str] = None


@router.post("/carve")
def carve(req: CarveRequest):
    """Save a user-specified byte range as a new recovered file."""
    sf = _require(req.file_id)
    data = Path(sf.stored_path).read_bytes()
    chunk = data[req.offset:req.offset + req.size]
    if not chunk:
        raise HTTPException(400, "Empty byte range")
    name = req.name or f"carve_{req.offset}_{req.size}.bin"
    out = storage.store_extracted(chunk, name, parent_id=sf.id,
                                  meta={"method": "manual_carve", "offset": req.offset})
    return {"file_id": out.id, "name": out.name, "size": out.size, "format": out.format}


@router.post("/carve-auto/{file_id}")
def carve_auto(file_id: str):
    """Carve every detectable embedded file and store each one."""
    sf = _require(file_id)
    data = Path(sf.stored_path).read_bytes()
    carved = signatures.carve(data, max_files=50)
    stored = []
    for c in carved:
        if c["offset"] == 0 and c["size"] >= sf.size - 8:
            continue  # the container itself
        out = storage.store_extracted(c["data"], f"carved_{c['name']}_{c['offset']}.{c['ext']}",
                                      parent_id=sf.id,
                                      meta={"method": "signature_carve", "offset": c["offset"]})
        stored.append({"file_id": out.id, "name": out.name, "offset": c["offset"],
                       "size": c["size"], "format": c["name"]})
    return {"carved": stored, "count": len(stored)}


@router.get("/archive/{file_id}")
def archive_list(file_id: str):
    sf = _require(file_id)
    data = Path(sf.stored_path).read_bytes()
    return payload_mod.list_archive(data)


class ArchiveExtractRequest(BaseModel):
    file_id: str
    entry: str
    password: Optional[str] = None


@router.post("/archive/extract")
def archive_extract(req: ArchiveExtractRequest):
    sf = _require(req.file_id)
    data = Path(sf.stored_path).read_bytes()
    try:
        content = payload_mod.extract_archive_entry(data, req.entry, req.password)
    except (KeyError, RuntimeError) as e:
        raise HTTPException(400, f"Could not extract entry: {e}")
    name = Path(req.entry).name or "archive_entry.bin"
    out = storage.store_extracted(content, name, parent_id=sf.id,
                                  meta={"method": "archive_extract", "entry": req.entry})
    return {"file_id": out.id, "name": out.name, "size": out.size, "format": out.format}


@router.get("/recursive/{file_id}")
def recursive(file_id: str, max_depth: int = 3):
    """Recursively carve/analyse a payload and its children (bounded)."""
    sf = _require(file_id)
    results = []
    seen: set[str] = set()

    def walk(fid: str, depth: int):
        if depth > max_depth or fid in seen:
            return
        seen.add(fid)
        cur = storage.get(fid)
        if cur is None:
            return
        data = Path(cur.stored_path).read_bytes()
        analysis = payload_mod.analyse_blob(data)
        node = {
            "file_id": fid, "name": cur.name, "format": cur.format, "depth": depth,
            "size": cur.size, "signatures": analysis["signatures"][:20],
            "interesting": analysis["interesting"], "children": [],
        }
        for c in analysis["carved_data"]:
            if c["offset"] == 0 and c["size"] >= cur.size - 8:
                continue
            child = storage.store_extracted(
                c["data"], f"rec_{c['name']}_{c['offset']}.{c['ext']}", parent_id=fid,
                meta={"method": "recursive_carve", "offset": c["offset"]})
            node["children"].append(child.id)
            walk(child.id, depth + 1)
        results.append(node)

    walk(sf.id, 0)
    return {"root": sf.id, "nodes": results}
