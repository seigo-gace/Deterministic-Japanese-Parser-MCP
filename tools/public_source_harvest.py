#!/usr/bin/env python3
"""Acquisition-only source harvester.

It fetches only entries explicitly listed in manifest["harvest_now"] and stores
raw bytes plus Source Lock evidence. It does not normalize, enrich, review,
compile, or promote data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

USER_AGENT = "Deterministic-Japanese-Parser-MCP-source-harvest/1.0"

def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("phase") != "ACQUISITION_ONLY":
        raise SystemExit("HARVEST_PHASE_MISMATCH")
    policy = data.get("policy") or {}
    if policy.get("normalize") is not False or policy.get("semantic_enrichment") is not False or policy.get("runtime_promotion") is not False:
        raise SystemExit("HARVEST_BOUNDARY_MISSING")
    ids = [row[0] for row in data.get("catalog", [])]
    if not ids or len(ids) != len(set(ids)):
        raise SystemExit("HARVEST_CATALOG_IDS_INVALID")
    direct = [item.get("id") for item in data.get("harvest_now", [])]
    if len(direct) != len(set(direct)):
        raise SystemExit("HARVEST_DIRECT_IDS_DUPLICATE")
    if not set(direct).issubset(set(ids)):
        raise SystemExit("HARVEST_DIRECT_NOT_IN_CATALOG")
    for item in data.get("harvest_now", []):
        if not str(item.get("url", "")).startswith("https://"):
            raise SystemExit(f"HARVEST_URL_INVALID:{item.get('id')}")
        if not item.get("filename") or "/" in item["filename"]:
            raise SystemExit(f"HARVEST_FILENAME_INVALID:{item.get('id')}")
    return data

def direct_entry(manifest: dict, source_id: str) -> dict:
    for item in manifest["harvest_now"]:
        if item["id"] == source_id:
            return item
    raise SystemExit(f"HARVEST_SOURCE_NOT_DIRECT:{source_id}")

def catalog_entry(manifest: dict, source_id: str) -> dict:
    fields = manifest["catalog_fields"]
    for row in manifest["catalog"]:
        if row[0] == source_id:
            return dict(zip(fields, row))
    raise SystemExit(f"HARVEST_SOURCE_UNKNOWN:{source_id}")

def self_test() -> None:
    sample = {
        "phase":"ACQUISITION_ONLY",
        "policy":{"normalize":False,"semantic_enrichment":False,"runtime_promotion":False},
        "catalog_fields":["id","name","status","homepage"],
        "catalog":[["x","X","harvest_now","https://example.invalid/"]],
        "harvest_now":[{"id":"x","url":"https://example.invalid/x.txt","filename":"x.txt"}],
    }
    p = Path("/tmp/public-source-harvest-self-test.json")
    p.write_text(json.dumps(sample), encoding="utf-8")
    m = load_manifest(p)
    assert direct_entry(m, "x")["filename"] == "x.txt"
    assert catalog_entry(m, "x")["name"] == "X"
    assert hashlib.sha256(b"abc").hexdigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    p.unlink(missing_ok=True)
    print(json.dumps({"status":"PASS","tests":4}))

def list_sources(path: Path) -> None:
    m = load_manifest(path)
    by_status = {}
    for row in m["catalog"]:
        by_status[row[2]] = by_status.get(row[2], 0) + 1
    print(json.dumps({
        "total_sources":len(m["catalog"]),
        "harvest_now_count":len(m["harvest_now"]),
        "harvest_now":[x["id"] for x in m["harvest_now"]],
        "by_status":dict(sorted(by_status.items())),
    }, ensure_ascii=False, sort_keys=True))

def acquire(path: Path, source_id: str, output_root: Path) -> None:
    m = load_manifest(path)
    spec = direct_entry(m, source_id)
    cat = catalog_entry(m, source_id)
    out = output_root / source_id
    out.mkdir(parents=True, exist_ok=True)
    target = out / spec["filename"]
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(spec["url"], headers={"User-Agent":USER_AGENT,"Accept":"*/*"})
    sha = hashlib.sha256()
    total = 0
    headers = {}
    started = time.time()
    final_url = spec["url"]
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as f:
            final_url = response.geturl()
            headers = {k.lower():v for k,v in response.headers.items()}
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                total += len(chunk)
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    evidence = {
        "schema_version":"1.0.0",
        "change_unit":m["change_unit"],
        "phase":"ACQUISITION_ONLY",
        "source":cat,
        "requested_url":spec["url"],
        "final_url":final_url,
        "filename":target.name,
        "bytes":total,
        "sha256":sha.hexdigest(),
        "elapsed_seconds":round(time.time()-started,3),
        "http":{"content_type":headers.get("content-type"),"content_length":headers.get("content-length"),"etag":headers.get("etag"),"last_modified":headers.get("last-modified")},
        "boundaries":{"normalized":False,"semantic_enrichment":False,"reviewed":False,"runtime_promoted":False},
    }
    (out/"source-lock.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(evidence,ensure_ascii=False,sort_keys=True))

def main() -> None:
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("self-test")
    q=sub.add_parser("list"); q.add_argument("--manifest",type=Path,required=True)
    q=sub.add_parser("acquire"); q.add_argument("--manifest",type=Path,required=True); q.add_argument("--source-id",required=True); q.add_argument("--output-root",type=Path,required=True)
    a=p.parse_args()
    if a.cmd=="self-test": self_test()
    elif a.cmd=="list": list_sources(a.manifest)
    else: acquire(a.manifest,a.source_id,a.output_root)

if __name__=="__main__":
    main()
