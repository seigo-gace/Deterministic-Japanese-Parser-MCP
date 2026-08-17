#!/usr/bin/env python3
from __future__ import annotations
import argparse,gzip,hashlib,json,sqlite3,sys
from pathlib import Path
from typing import Any,Iterable

def unique(v:Iterable[Any])->list[str]: return sorted({str(x).strip() for x in v if x is not None and str(x).strip()})
def sha(p:Path):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def connect(path:Path):
 return sqlite3.connect(path,isolation_level=None)
def init(path:Path):
 path.parent.mkdir(parents=True,exist_ok=True);path.unlink(missing_ok=True);db=connect(path)
 db.executescript('''PRAGMA page_size=32768;PRAGMA journal_mode=OFF;PRAGMA synchronous=OFF;PRAGMA temp_store=FILE;PRAGMA cache_size=-262144;PRAGMA locking_mode=EXCLUSIVE;
 CREATE TABLE records(seq INTEGER PRIMARY KEY,record_id TEXT NOT NULL,lemma TEXT NOT NULL,reading TEXT NOT NULL,pos_json BLOB NOT NULL,domains_json BLOB NOT NULL,source_dataset TEXT NOT NULL,source_version TEXT NOT NULL,source_license TEXT NOT NULL);
 CREATE TABLE surface_lookup(surface TEXT NOT NULL,record_seq INTEGER NOT NULL);
 CREATE TABLE reading_lookup(reading TEXT NOT NULL,record_seq INTEGER NOT NULL);
 CREATE TABLE build_state(part_number INTEGER PRIMARY KEY,record_count INTEGER NOT NULL);
 ''');db.close()
def append(path,manifest,input_root,parts):
 m=json.loads(manifest.read_text(encoding='utf-8'));date=str(m.get('date') or '');items=m['parts'];db=connect(path);db.executescript('PRAGMA journal_mode=OFF;PRAGMA synchronous=OFF;PRAGMA temp_store=FILE;PRAGMA cache_size=-262144;PRAGMA locking_mode=EXCLUSIVE;BEGIN;')
 n=int(db.execute('select coalesce(max(seq),0) from records').fetchone()[0]);rec=[];sur=[];rea=[]
 done={r[0] for r in db.execute('select part_number from build_state')}
 for partno in parts:
  if partno in done: print(f'skip part={partno:02d}',file=sys.stderr);continue
  it=items[partno-1];p=input_root/it['file'];before=n
  with gzip.open(p,'rb') as f:
   for line in f:
    if not line.strip():continue
    x=json.loads(line);n+=1;rid=str(x['entry_id']);lemma=str(x.get('lemma') or x.get('surface') or '');reading=str(x.get('reading') or '').strip();pos=x.get('pos');posv=unique(pos if isinstance(pos,list) else [pos]);dom=unique(x.get('domains') or []);ds='+'.join(unique(x.get('source_datasets') or [])) or 'MCP completed runtime data';rights='+'.join(unique(x.get('rights_lanes') or [])) or 'source rights preserved in completed-data manifest'
    rec.append((n,rid,lemma,reading,json.dumps(posv,ensure_ascii=False,separators=(',',':')).encode('utf-8'),json.dumps(dom,ensure_ascii=False,separators=(',',':')).encode('utf-8'),ds,date,rights));sur.extend((s,n) for s in unique([x.get('surface'),x.get('lemma'),*(x.get('aliases') or [])]));
    if reading:rea.append((reading,n))
    if len(rec)>=20000:
     db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)',rec);db.executemany('INSERT INTO surface_lookup VALUES (?,?)',sur);db.executemany('INSERT INTO reading_lookup VALUES (?,?)',rea);rec.clear();sur.clear();rea.clear()
  if rec:
   db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)',rec);db.executemany('INSERT INTO surface_lookup VALUES (?,?)',sur);db.executemany('INSERT INTO reading_lookup VALUES (?,?)',rea);rec.clear();sur.clear();rea.clear()
  actual=n-before;decl=int(it['records']);
  if actual!=decl: raise ValueError(f'part {partno} count {actual}!={decl}')
  db.execute('insert into build_state(part_number,record_count) values (?,?)',(partno,actual));print(f'loaded part={partno:02d} part_records={actual} total={n}',file=sys.stderr,flush=True)
 db.execute('COMMIT');db.close()
def finalize(path,manifest,out_manifest):
 m=json.loads(manifest.read_text(encoding='utf-8'));expected=int((m.get('validation') or {}).get('full_json_records_validated'));date=str(m.get('date') or '');msha=sha(manifest);db=connect(path);db.executescript('PRAGMA journal_mode=OFF;PRAGMA synchronous=OFF;PRAGMA temp_store=FILE;PRAGMA cache_size=-262144;PRAGMA locking_mode=EXCLUSIVE;')
 c=int(db.execute('select count(*) from records').fetchone()[0]);parts=int(db.execute('select count(*) from build_state').fetchone()[0]);
 if c!=expected or parts!=len(m['parts']):raise ValueError(f'incomplete lexical build records={c}/{expected} parts={parts}/{len(m["parts"])}')
 print('creating indexes',file=sys.stderr,flush=True);db.executescript('CREATE UNIQUE INDEX records_record_id ON records(record_id);CREATE INDEX surface_lookup_surface ON surface_lookup(surface,record_seq);CREATE INDEX reading_lookup_reading ON reading_lookup(reading,record_seq);ANALYZE;')
 print('integrity_check',file=sys.stderr,flush=True);ok=db.execute('PRAGMA integrity_check').fetchone()[0]
 if ok!='ok':raise ValueError(ok)
 us=int(db.execute('select count(distinct surface) from surface_lookup').fetchone()[0]);ur=int(db.execute('select count(distinct reading) from reading_lookup').fetchone()[0]);hg=int(db.execute('select count(*) from (select surface from surface_lookup group by surface having count(*)>1)').fetchone()[0]);db.close()
 man={'schema_version':'1.2.0','compiler_version':'completed-data-openlexicon-sqlite-v2','mode':'compiled_lexical_identity_only','lookup_backend':'sqlite-index-v2','record_count':c,'expected_record_count':c,'record_shards':0,'source_versions':[date],'source_licenses':['mixed; preserved by completed-data rights_lanes'],'exact_lookup_only':True,'reading_alias_promotion':False,'semantic_auto_promotion':False,'intent_auto_promotion':False,'external_action_auto_promotion':False,'direct_final_runtime':True,'factory_used':False,'source_manifest_sha256':msha,'unique_surfaces':us,'unique_readings':ur,'homograph_surfaces':hg,'sqlite':{'path':path.name,'sha256':sha(path),'bytes':path.stat().st_size},'boundaries':{'existing_runtime':'OpenLexiconRuntime','parallel_runtime':False,'parser_logic_changed':False,'meaning_generation':False,'factory_used':False}}
 out_manifest.parent.mkdir(parents=True,exist_ok=True);out_manifest.write_bytes((json.dumps(man,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8'));print(json.dumps({'records':c,'parts':parts,'unique_surfaces':us,'unique_readings':ur,'homographs':hg,'bytes':path.stat().st_size,'integrity':ok}),flush=True)
def main():
 ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
 p=sp.add_parser('init');p.add_argument('--db',type=Path,required=True)
 p=sp.add_parser('append');p.add_argument('--db',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--input-root',type=Path,required=True);p.add_argument('--parts',type=int,nargs='+',required=True)
 p=sp.add_parser('finalize');p.add_argument('--db',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out-manifest',type=Path,required=True)
 a=ap.parse_args(); {'init':lambda:init(a.db),'append':lambda:append(a.db,a.manifest,a.input_root,a.parts),'finalize':lambda:finalize(a.db,a.manifest,a.out_manifest)}[a.cmd]()
if __name__=='__main__':main()
