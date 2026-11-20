"""Extract actual post-merge parent ports cited by later selected numeric bindings."""
import argparse
import json
from pathlib import Path

import numpy as np


def summarize(study):
    result={}
    for key in json.loads((study/'results.json').read_bytes()):
        name,seed=key.split('/')
        with np.load(study/f'{name}-{seed}-visible-port'/'numeric.npz') as data:
            f,args,out,ports=[data[k] for k in ('features','args','outcomes','input_ports')]
            examples=[];all_edges=conflicts=both=0
            for i in np.flatnonzero((f[:,11]>0)&(f[:,13]>0)):
                child=int(f[i,13]);c=out[child-1]
                for position,(address,parent) in enumerate(ports[i]):
                    if not parent:continue
                    p=out[parent-1]
                    assert 0<p[0]<c[0] and p[5]==args[i,position] and p[9]==address-1
                    all_edges+=1
                    if p[4]==p[5]:continue
                    conflicts+=1;both+=int(p[8]==1 and c[8]==1)
                    event=dict(parent_rhs=int(parent),parent_run=int(p[0]),parent_rule=int(p[1]),
                               parent_selected=bool(p[8]==1),source_row=int(p[9]),parent_key=int(p[13]),
                               prior_value=int(p[3]),candidate=int(p[4]),visible=int(p[5]),parent_write=bool(p[6]),
                               child_rhs=child,child_run=int(c[0]),child_rule=int(c[1]),operand_position=position,
                               consumed=int(args[i,position]),child_candidate=int(c[4]),child_visible=int(c[5]),child_write=bool(c[6]))
                    examples.append(event)
            examples.sort(key=lambda t:(not t['parent_selected'],t['child_rhs']))
            result[key]=dict(edges=all_edges,losing_candidate_edges=conflicts,both_selected_losing_edges=both,examples=examples[:5])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('study',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();a.out.write_text(json.dumps(summarize(a.study),indent=1)+'\n')
