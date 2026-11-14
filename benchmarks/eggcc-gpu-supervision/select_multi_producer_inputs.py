"""Deterministic synthetic coverage probe, never selected by real-run labels."""
import argparse,hashlib,json
from pathlib import Path


def select(rows,excluded,per_interface):
    if per_interface<1:raise ValueError('positive per-interface count required')
    buckets={}
    for row in rows:
        if row['input_sha256'] in excluded:continue
        producers=row['producer']
        if not isinstance(producers,list) or len(producers)!=2:raise ValueError('two producers required')
        key=(*producers,row['consumer'])
        buckets.setdefault(key,{})[row['input_sha256']]=row
    selected={};coverage=[]
    for key,bucket in sorted(buckets.items()):
        identities=sorted(bucket)[:per_interface]
        for identity in identities:selected.setdefault(identity,bucket[identity])
        coverage.append(dict(producers=list(key[:2]),consumer=key[2],available=len(bucket),selected=identities))
    return [selected[k] for k in sorted(selected)],coverage


def main():
    p=argparse.ArgumentParser();p.add_argument('enumeration',type=Path);p.add_argument('existing_selection',type=Path);p.add_argument('output',type=Path);p.add_argument('--per-interface',type=int,default=1);a=p.parse_args()
    source=a.enumeration/'cases.jsonl';rows=[json.loads(s) for s in source.read_text().splitlines()]
    existing=json.loads(a.existing_selection.read_text());excluded={r['input_sha256'] for r in existing['included']}
    chosen,coverage=select(rows,excluded,a.per_interface)
    a.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((a.enumeration/'manifest.json').read_text())
    manifest['selection']=dict(policy='lexicographically smallest input hashes per ordered producer-pair and consumer; exclude existing inputs; no accuracy selection',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),existing_sha256=hashlib.sha256(a.existing_selection.read_bytes()).hexdigest(),per_interface=a.per_interface,inputs=len(chosen),coverage=coverage)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (a.output/'cases.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in chosen))
    print(json.dumps(dict(inputs=len(chosen),interfaces=len(coverage))))

if __name__=='__main__':main()
