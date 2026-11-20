"""Validate joint per-id root/child evidence and preserve compact independently inspectable root receipts."""
import argparse,gzip,hashlib,json
from pathlib import Path


def read(path):return json.loads(path.read_bytes())
def main(a):
    report={}
    for key,arms in read(a.data/'results.json').items():
        case,seed,regime=key.split('/')
        with gzip.open(a.data/f'{case}-{seed}-{regime}-use-evidence.json.gz','rt') as f:proof=json.load(f)
        root=proof['roots'];native={r[1]:r for r in proof['allocations'] if not r[4]}
        assert len(native)==arms['use']['fresh']
        checked={r[2]:r for r in root['commits']}
        primary={};child={};examples={}
        for id_,ordinal,rid,template,provider,serial in root['fresh']:
            assert native[id_]==[ordinal,id_,template,template,False]
            ticket=checked[serial];assert ticket[:5]==[ordinal,provider,serial,rid,template]
            assert id_ not in primary;primary[id_]=(ordinal,template,provider,serial)
            if len(ticket[6]) and provider not in examples:
                examples[provider]=dict(fresh_id=id_,ordinal=ordinal,rule=rid,physical_template=template,raw_recipe_serial=serial,
                    provider=provider,source_run=ticket[5],sealed_source_ports=ticket[6],resolved_inputs=ticket[7])
        for c in proof['children']:
            id_=c['allocated']
            if id_ is None:continue
            parent=c['parent']
            assert id_ not in primary and id_ not in child
            assert native[id_][0]==parent['ordinal'] and native[id_][2]==c['template'] and not native[id_][4]
            child[id_]=(c['template'],parent['ordinal'])
        matched=set(primary)|set(child)
        assert len(matched)==arms['use']['direct_distinct']
        combined_hash=hashlib.sha256(json.dumps(sorted(matched),separators=(',',':')).encode()).hexdigest()
        report[key]=dict(wire_bytes=root['wire_bytes'],wire_hash=root['wire_hash'],issued=root['emitted'],verified=root['sealed'],
            consumed=len(checked),distinct_root_ids=len(primary),distinct_child_ids=len(child),fresh_id_union_sha256=combined_hash,
            uncovered_ids=sorted(set(native)-matched),examples=examples)
    a.out.write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('out',type=Path);main(p.parse_args())
