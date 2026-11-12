"""Merge saved disjoint collection chunks, preserving runner/input provenance."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
seen=set();cases=[];chunks=[]
for path in a.inputs:
    data=json.loads(path.read_text())
    for row in data['cases']:
        if row['id'] in seen:raise ValueError('duplicate collection ID')
        seen.add(row['id']);cases.append(row)
    chunks.append(dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),collection=data.get('collection'),cases=len(data['cases'])))
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(dict(cases=cases,collection_chunks=chunks),separators=(',',':')))
print('merged',len(cases))
