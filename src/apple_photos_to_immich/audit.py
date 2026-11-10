"""Read-only audit of exported media. Only writes the report to meta_dir."""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path
from .config import Config
from .matching import extract_uuid

MEDIA={".jpg",".jpeg",".heic",".heif",".png",".gif",".tiff",".tif",".dng",".raw",".arw",".cr2",".cr3",".nef",".rw2",".orf",".webp",".bmp",".mov",".mp4",".m4v",".avi",".mts",".3gp",".mpg",".mpeg"}

def audit_export(config: Config, logger: logging.Logger, *, sha256: bool=False) -> int:
    root=config.export_dir
    if not root.is_dir():
        logger.error("Export folder missing: %s",root)
        return 1
    config.meta_dir.mkdir(parents=True,exist_ok=True)
    ext=Counter()
    uuids=Counter()
    hashes=[]
    errors=[]
    count=total=0
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in MEDIA:
            continue
        try:
            count+=1
            size=p.stat().st_size
            total+=size
            ext[p.suffix.lower()]+=1
            uid=extract_uuid(p.name)
            if uid: uuids[uid]+=1
            if sha256:
                h=hashlib.sha256()
                with p.open("rb") as f:
                    for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
                hashes.append({"path":str(p.relative_to(root)),"bytes":size,"sha256":h.hexdigest()})
            if count%2000==0:logger.info("Audited %d media files",count)
        except OSError as exc:
            errors.append({"path":str(p),"error":str(exc)})
    repeats={k:n for k,n in uuids.items() if n>1}
    report={"exportDir":str(root),"mediaFiles":count,"totalBytes":total,
            "extensions":dict(ext),"uniqueUuidNames":len(uuids),
            "reusedUuidCount":len(repeats),"reusedUuidExamples":dict(list(repeats.items())[:50]),
            "note":"Repeated UUIDs may be Live Photos, originals or edits; not necessarily duplicates.",
            "sha256Enabled":sha256,"sha256Files":hashes,"errors":errors}
    dest=config.meta_dir/"audit-export.json"
    temp=dest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    temp.replace(dest)
    logger.info("Export audit: %d files, %.2f GB, %d errors; %s",count,total/1e9,len(errors),dest)
    return 2 if errors or not count else 0
