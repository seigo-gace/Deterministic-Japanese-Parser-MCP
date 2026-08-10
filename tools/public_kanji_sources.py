#!/usr/bin/env python3
"""Acquire KANJIDIC2 + Unicode Unihan without dropping meaning-less source rows."""
from __future__ import annotations
import argparse, gzip, hashlib, json, shutil, unicodedata, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

UA = "Deterministic-Japanese-Parser-MCP/public-kanji-semantic-acquisition"

def norm(v: Any) -> str: return unicodedata.normalize("NFKC", str(v or "")).strip()
def jl(v: Any) -> str: return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def digest(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()
def download(url: str, p: Path) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(Request(url, headers={"User-Agent":UA}), timeout=180) as r, p.open("wb") as f:
        shutil.copyfileobj(r, f, 1024*1024)
    return digest(p)
def load(p: Path) -> dict[str, Any]: return json.loads(p.read_text(encoding="utf-8"))
def save(p: Path, v: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
def spec(m: dict[str, Any], sid: str) -> dict[str, Any]:
    xs=[x for x in m.get("sources",[]) if x.get("id")==sid]
    if len(xs)!=1 or xs[0].get("status")!="enabled": raise RuntimeError(f"enabled source not unique: {sid}")
    return xs[0]
def verify(s: dict[str, Any], actual: str) -> None:
    expected=norm(s.get("expected_source_sha256"))
    if expected and expected.casefold()!=actual.casefold():
        raise RuntimeError(f"source digest mismatch: {s['id']} expected={expected} actual={actual}")
def write_jsonl(p: Path, rows: list[dict[str, Any]]) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for row in sorted(rows, key=lambda x:x["id"]): f.write(jl(row)+"\n")
    return digest(p)

def unihan(asset: Path, s: dict[str, Any], source_sha: str, out: Path) -> tuple[dict[str, Any], set[str]]:
    props: dict[str, dict[str,str]]={}
    with zipfile.ZipFile(asset) as z:
        names=sorted(n for n in z.namelist() if n.startswith("Unihan") and n.endswith(".txt"))
        if not names: raise RuntimeError("Unihan text files missing")
        for name in names:
            with z.open(name) as f:
                for raw in f:
                    text=raw.decode("utf-8").strip()
                    if not text or text.startswith("#"): continue
                    parts=text.split("\t",2)
                    if len(parts)!=3 or parts[1] not in {"kDefinition","kJapaneseOn","kJapaneseKun"}: continue
                    props.setdefault(parts[0],{})[parts[1]]=norm(parts[2])
    rows=[]; surfaces=set()
    for cp, values in props.items():
        definition=norm(values.get("kDefinition"))
        if not definition: continue
        try: literal=chr(int(cp.removeprefix("U+"),16))
        except ValueError: continue
        surfaces.add(literal)
        readings=[]
        for key in ("kJapaneseOn","kJapaneseKun"): readings += norm(values.get(key)).split()
        rows.append({"id":f"UNIHAN-{cp}","surface":literal,"readings":sorted(set(readings)),"part_of_speech":["kanji"],
          "meanings":[definition],"label":definition,"domains":["kanji","han-ideograph","unicode-unihan"],
          "dataset":s["title"],"license":s["license"],"source_id":cp,"source_url":s["homepage"],"source_sha256":source_sha,
          "attribution":s.get("attribution",""),"parameters":{"meaning_language":"en","kJapaneseOn":norm(values.get("kJapaneseOn")),"kJapaneseKun":norm(values.get("kJapaneseKun"))}})
    if not rows: raise RuntimeError("Unihan kDefinition produced no records")
    normalized_sha=write_jsonl(out,rows)
    return {"source_id":s["id"],"records":len(rows),"missing_meaning_records":0,"normalized_sha256":normalized_sha,"source_sha256":source_sha}, surfaces

def kanjidic(asset: Path, s: dict[str, Any], source_sha: str, out: Path, unresolved: Path) -> tuple[dict[str, Any], set[str]]:
    xml=out.parent/"kanjidic2.xml"; out.parent.mkdir(parents=True,exist_ok=True); unresolved.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(asset,"rb") as src, xml.open("wb") as dst: shutil.copyfileobj(src,dst,1024*1024)
    rows=[]; missing=[]; header={}
    try:
        root=ET.parse(xml).getroot(); he=root.find("header")
        if he is not None: header={c.tag:norm(c.text) for c in he}
        for ch in root.findall("character"):
            literal=norm(ch.findtext("literal"))
            if not literal: continue
            rm=ch.find("reading_meaning"); readings=[]; meanings=[]; nanori=[]
            if rm is not None:
                nanori=[norm(x.text) for x in rm.findall("nanori") if norm(x.text)]
                for g in rm.findall("rmgroup"):
                    readings += [norm(x.text) for x in g.findall("reading") if norm(x.text)]
                    meanings += [norm(x.text) for x in g.findall("meaning") if x.get("m_lang") is None and norm(x.text)]
            readings=sorted(set(readings)); meanings=sorted(set(meanings)); nanori=sorted(set(nanori)); cp=f"U+{ord(literal):04X}"
            misc=ch.find("misc"); meta={"nanori":nanori}
            if misc is not None: meta.update({"stroke_count":[norm(x.text) for x in misc.findall("stroke_count") if norm(x.text)],"grade":norm(misc.findtext("grade")) or None,"frequency_rank":norm(misc.findtext("freq")) or None,"jlpt_legacy":norm(misc.findtext("jlpt")) or None})
            base={"id":f"KANJIDIC2-{ord(literal):06X}","surface":literal,"readings":readings,"part_of_speech":["kanji"],"dataset":s["title"],"license":s["license"],"source_id":cp,"source_url":s["homepage"],"source_sha256":source_sha,"attribution":s.get("attribution",""),"parameters":meta}
            if meanings:
                rows.append({**base,"meanings":meanings,"label":meanings[0],"domains":["kanji","character"],"parameters":{**meta,"meaning_language":"en"}})
            else:
                missing.append({**base,"meaning_status":"missing-in-kanjidic2"})
    finally: xml.unlink(missing_ok=True)
    out_sha=write_jsonl(out,rows); unresolved_sha=write_jsonl(unresolved,missing)
    return {"source_id":s["id"],"source_character_records":len(rows)+len(missing),"records":len(rows),"missing_meaning_records":len(missing),"normalized_sha256":out_sha,"unresolved_sha256":unresolved_sha,"source_sha256":source_sha,"source_header":header}, {x["surface"] for x in missing}

def acquire(mp: Path, root: Path, reportp: Path, lockp: Path) -> dict[str, Any]:
    m=load(mp); us=spec(m,"unicode-unihan-17.0.0"); ks=spec(m,"kanjidic2")
    raw=root/"raw"; ref=root/"reference"; unr=root/"unresolved"; lic=root/"licenses"
    ua=raw/"unicode-unihan-17.0.0.zip"; ka=raw/"kanjidic2.xml.gz"
    ush=download(us["url"],ua); ksh=download(ks["url"],ka); verify(us,ush); verify(ks,ksh)
    ur, u_surfaces=unihan(ua,us,ush,ref/"unicode-unihan-17.0.0.jsonl")
    kr, k_missing=kanjidic(ka,ks,ksh,ref/"kanjidic2.jsonl",unr/"kanjidic2-missing-meaning.jsonl")
    covered=k_missing & u_surfaces; uncovered=k_missing-u_surfaces
    for s in (us,ks):
        if norm(s.get("license_url")): download(s["license_url"],lic/f"{s['id']}-LICENSE.txt")
    report=load(reportp) if reportp.exists() else {"sources":[],"meaning_complete":True,"llm_api_used":False,"web_scraping_used":False}
    report["sources"]=[x for x in report.get("sources",[]) if x.get("source_id") not in {us["id"],ks["id"]}]+[ur,kr]
    report["enabled_source_count"]=len(report["sources"]); report["total_records"]=sum(int(x.get("records",0)) for x in report["sources"])
    report["cross_source_coverage"]={"target_source":ks["id"],"fallback_source":us["id"],"target_source_rows":kr["source_character_records"],"target_direct_meaning_records":kr["records"],"target_missing_meaning_records":kr["missing_meaning_records"],"fallback_covered_records":len(covered),"uncovered_records":len(uncovered),"uncovered_sample":sorted(uncovered)[:50],"unresolved_inventory":"unresolved/kanjidic2-missing-meaning.jsonl","unresolved_inventory_sha256":kr["unresolved_sha256"]}
    report["meaning_complete"]=bool(report.get("meaning_complete",True)) and not uncovered; report["llm_api_used"]=False; report["web_scraping_used"]=False; save(reportp,report)
    locks=load(lockp) if lockp.exists() else {"sources":[]}; locks["sources"]=[x for x in locks.get("sources",[]) if x.get("source_id") not in {us["id"],ks["id"]}]
    for s,source_sha,path,r in ((us,ush,ref/"unicode-unihan-17.0.0.jsonl",ur),(ks,ksh,ref/"kanjidic2.jsonl",kr)):
        lf=lic/f"{s['id']}-LICENSE.txt"; locks["sources"].append({"source_id":s["id"],"adapter":s["adapter"],"version":s.get("version"),"source_url":s["url"],"source_sha256":source_sha,"expected_source_sha256":s.get("expected_source_sha256"),"lock_state":"authoritative-manifest-digest" if s.get("expected_source_sha256") else "computed-digest-needs-canonical-lock","license":s.get("license"),"license_url":s.get("license_url"),"license_sha256":digest(lf) if lf.exists() else None,"attribution":s.get("attribution",""),"normalized_path":str(path.relative_to(root)),"normalized_sha256":r["normalized_sha256"],"records":r["records"]})
    save(lockp,locks)
    print(jl({"unihan_records":ur["records"],"kanjidic_source_rows":kr["source_character_records"],"kanjidic_direct_meaning":kr["records"],"kanjidic_missing":kr["missing_meaning_records"],"fallback_covered":len(covered),"uncovered":len(uncovered),"meaning_complete":report["meaning_complete"],"unihan_source_sha256":ush,"kanjidic_source_sha256":ksh}))
    return report

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--output-root",type=Path,required=True); p.add_argument("--report",type=Path,required=True); p.add_argument("--lock",type=Path,required=True); a=p.parse_args(); acquire(a.manifest,a.output_root,a.report,a.lock); return 0
if __name__=="__main__": raise SystemExit(main())
