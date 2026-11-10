"""Read-only comparison of Apple Photos date/GPS against Immich's API."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from .config import Config
from .commands import ensure_album_map, build_match_report, _make_client

def numeric(value: Any) -> float | None:
    try:return float(value) if value is not None and value!="" else None
    except (TypeError, ValueError):return None

def iso_day(value: Any) -> str | None:
    if not value:return None
    s=str(value)
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).date().isoformat()
    except ValueError:return s[:10] if len(s)>=10 else None

def verify_metadata(config: Config, logger: logging.Logger, *, limit: int=300, all_assets: bool=False) -> int:
    if limit<1:raise ValueError("Sample size must be positive")
    if ensure_album_map(config,logger):return 1
    source=json.loads(config.album_map_path.read_text(encoding="utf-8"))["assets"]
    client=_make_client(config,logger)
    matched=build_match_report(config,client,logger)["uuidToAssetId"]
    pairs=[(k,v) for k,v in matched.items() if k in source]
    if not all_assets and len(pairs)>limit:
        pairs=pairs[::max(1,len(pairs)//limit)][:limit]
    counts={"gpsMissing":0,"gpsMismatch":0,"dateMissing":0,"dateMismatch":0}
    errors=[]
    examples=[]
    checked=0
    for uuid,asset_id in pairs:
        try:
            target=client.request("GET",f"/assets/{asset_id}") or {}
            exif=target.get("exifInfo") or {}
            if not isinstance(exif,dict):exif={}
            original=source[uuid]
            problems=[]
            slat=numeric(original.get("latitude")); slon=numeric(original.get("longitude"))
            tlat=numeric(exif.get("latitude")); tlon=numeric(exif.get("longitude"))
            if slat is not None and slon is not None:
                if tlat is None or tlon is None:
                    counts["gpsMissing"]+=1;problems.append("gps_missing")
                elif abs(slat-tlat)>0.0005 or abs(slon-tlon)>0.0005:
                    counts["gpsMismatch"]+=1;problems.append("gps_mismatch")
            sd=iso_day(original.get("date"))
            td=iso_day(exif.get("dateTimeOriginal") or target.get("localDateTime") or target.get("fileCreatedAt"))
            if sd and not td:counts["dateMissing"]+=1;problems.append("date_missing")
            elif sd and td and sd!=td:counts["dateMismatch"]+=1;problems.append("date_mismatch_timezone_possible")
            if problems and len(examples)<100:
                examples.append({"appleUuid":uuid,"assetId":asset_id,"issues":problems,"sourceDay":sd,"targetDay":td})
            checked+=1
        except (RuntimeError,KeyError,TypeError,ValueError) as exc:
            errors.append({"appleUuid":uuid,"error":str(exc)})
    report={"matchedTotal":len(matched),"checked":checked,"mode":"all" if all_assets else "sample",
            **counts,"errors":errors[:100],"issuesExamples":examples,
            "warning":"Calendar days may differ due to timezone. Review discrepancies manually."}
    dest=config.meta_dir/"metadata-verification.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    temp.replace(dest)
    logger.info("Metadata report %s (%d verified, %d API errors)",dest,checked,len(errors))
    return 2 if any(counts.values()) or errors else 0
