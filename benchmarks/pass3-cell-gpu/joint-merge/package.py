"""Check the final packet ABI against archived receipts and keep compact physical-id evidence."""
import argparse,gzip,hashlib,json
from pathlib import Path


def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest()
def main(a):
    first=read(a.first/'results.json');final=read(a.final/'results.json');report={}
    for key,arms in final.items():
        case,seed=key.split('/')
        for mode,result in arms.items():
            assert result==first[key][mode],(key,mode)
        with gzip.open(a.final/f'{case}-{seed}-learned-allocations.json.gz','rt') as f:r=json.load(f)
        physical={v[1]:v for v in r['cell_ids'] if not v[4]};rows=[];seen=set()
        for p in r['issued']:
            cell=p['allocated']
            if cell is None:continue
            assert not p['rejected'] and p['entered_allocator'] and p['issued_before_mutation']
            owner,actual,t,declared,recycled=physical[cell];parent=p['parent']
            assert (owner,actual,t,recycled)==(parent['ordinal'],cell,p['template'],False)
            assert t!=declared and cell not in seen;seen.add(cell)
            rows.append([cell,t,parent['ordinal'],declared,parent['provider'],parent['token'],p['effect'],p['id'],
                         p['candidate_site'],p['old_reference'],p['old_epoch'],p['candidate_reference'],p['candidate_epoch']])
        assert len(seen)==arms['learned']['extra_direct']
        report[key]=dict(columns=['fresh_id','child_template','parent_rhs','parent_template','source_provider','source_ticket',
                'effect','child_ticket','candidate_output_site','old_reference','old_epoch','candidate_reference','candidate_epoch'],
                fresh_allocation_stream_sha256=digest(r['cell_ids']),distinct_extra_ids_sha256=digest(sorted(seen)),children=rows)
    (a.out/'physical-ids.json').write_text(json.dumps(report,separators=(',',':'))+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('first','final','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
