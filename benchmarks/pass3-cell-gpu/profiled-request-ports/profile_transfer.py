"""Contemporaneous frozen-profile check: generic original-trained vs new activation-trained PGO images."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from joint_common import HOLDOUTS,file_digest,routes,session


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False)
    joint=json.loads((a.study/'joint-results.json').read_bytes())
    prior=json.loads((a.reference/'build.json').read_bytes())
    fit=json.loads((a.build/'joint-build.json').read_bytes())
    old=a.reference/'learned-use';new=a.build/'learned-use'
    assert file_digest(old)==prior['binaries']['learned-use']['sha256']
    assert file_digest(new)==fit['binaries']['use']['sha256']
    results={}
    for case in HOLDOUTS:
        program,plan,off,on=routes(a,case)
        rows={k:dict(ms=[],api_ms=[]) for k in ('original-trained','active-trained-off','active-trained-on')}
        with ExitStack() as stack:
            fun={k:stack.enter_context(session(old if k=='original-trained' else new,program,plan)) for k in rows}
            names=list(rows)
            for i in range(-1,4):
                pos=max(i,0)%3;order=names[pos:]+names[:pos]
                if i%2:order=order[::-1]
                for k in order:
                    activated=k=='active-trained-on'
                    ref=joint[case]['arms']['pgo-union' if activated else 'pgo-original']
                    t=perf_counter_ns();v=fun[k](on if activated else off);wall=(perf_counter_ns()-t)/1e6
                    assert v['runs']==ref['runs'] and v['state_sha']==ref['state_sha'] and v['multi']['total_rhs']==ref['rhs']
                    assert v['root_recipe']['allocated']==ref['root_allocated'] and v['multi']['counts']['raw_tuples']==ref['raw_count']
                    assert v['multi'].get('patch_ports',{}).get('union_repairs',0)==ref['patch']['union_repairs']
                    if i>=0:rows[k]['ms'].append(v['ms']);rows[k]['api_ms'].append(wall)
        for row in rows.values():row.update(median_ms=median(row['ms']),median_api_ms=median(row['api_ms']))
        results[case]=rows;(a.out/'profile-transfer.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(row['median_ms'],2)) for k,row in rows.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','reference','build','study','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;measure(a)
