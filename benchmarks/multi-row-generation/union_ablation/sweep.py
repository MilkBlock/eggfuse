"""Challenge every observed raw external endpoint pair with the neural producer online."""
import argparse
from itertools import product
import json
from pathlib import Path

import numpy as np
import torch

from engine import device_plan, run
from experiment import dataset, device, load_producer, study, upload, cpu
from audit_union import truth


@torch.inference_mode()
def sweep(producers):
    dev=device();templates,_,_,schema=study()
    model=load_producer(schema,1703,producers,dev)
    results={}
    for template in templates:
        base=dataset('test',template,8)
        source=6  # one public handle map; input events are replaced below
        cases=list(product(template['public_ports'],repeat=2))
        # Include every ordered read of the six physical endpoints.
        public=list(product((0,1),template['public_ports']))
        requests=list(product(public,repeat=2))
        count=len(cases)*9
        d={k:np.repeat(v[source:source+1],count,axis=0) if isinstance(v,np.ndarray) else v
           for k,v in base.items()}
        handles={(int(row[0]),int(p)):int(row[1]) for row,p in zip(d['a'][0],d['a_port'][0])}
        for n,(a,b) in enumerate(cases):
            for j in range(9):
                i=n*9+j
                d['external'][i]=[1,0,handles[0,a],1,handles[1,b]]
                d['external_ports'][i]=[a,b]
                for slot,((owner,l),(peer,r)) in enumerate(requests[j*4:j*4+4]):
                    d['requests'][i,slot]=[owner,handles[owner,l],peer,handles[peer,r],slot]
                    d['request_ports'][i,slot]=[l,r]
        x=upload(d,slice(None),dev)
        plan=device_plan(template['id'],dev)
        table=model.encoder.encode_bank(schema.bank(template,'pairwise',dev))
        stats={}
        for policy in ('immediate','fused_fenced','no_congruence'):
            first,stages,book=run(model,x,table,plan,policy,'each')
            # Download once after actual execution, then consult the native oracle.
            first=cpu(first);saved={tick:{k:v.cpu().numpy() for k,v in obs.items()}
                                    for tick,obs in stages.items()}
            failures=set();omitted=gained=secondary=correct=0
            for tick,s in saved.items():
                classes,legal,expected,extra=truth(d,tick)
                labels=s['classes'];got=s['active'].astype(bool)
                matrix=labels[:,:,None]==labels[:,None,:]
                bad=(matrix!=classes).any((1,2))|(got!=legal).any(1)
                ptr=s['pointers'][...,0];rows=np.arange(count)[:,None]
                witness=(first['rows'][rows,ptr,:2]==expected[...,:2]).all(-1)&first['active'][rows,ptr].astype(bool)
                fields=(s['rows']==expected).all(-1)
                bad|=(got&(~fields|~witness)).any(1)
                failures.update(i//9 for i in np.flatnonzero(bad))
                if tick==3:
                    omitted=int((legal&~got).sum());gained=int((~legal&got).sum())
                    secondary=int(extra.sum());correct=int((extra&got&fields&witness).sum())
            stats[policy]=dict(external_cases=len(cases),all_four_observers_exact=len(cases)-len(failures),
                               failed_cases=[cases[i] for i in sorted(failures)],missing_final_reads=omitted,
                               spurious_final_reads=gained,secondary_reads=secondary,completed_secondary_reads=correct)
            if policy!='no_congruence' and failures:raise ValueError((template['id'],policy,stats[policy]))
        results[template['id']]=stats
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('producers',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    args.output.write_text(json.dumps(sweep(args.producers),indent=2)+'\n')
