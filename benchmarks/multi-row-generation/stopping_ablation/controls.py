"""Counterfactual identical policy observations and independent GPU checkpoint resume."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from measure import LANES,load_gates
from queue_gpu import (Queue,checkpoint,restore,status,device,study,load_producer,dataset,
                       upload,inputs,device_plan,MAX_TICKS)


@torch.inference_mode()
def run(root,producers):
    dev=device();templates=study()[0];schema=study()[3];results={}
    for seed in (1703,1709):
        model=load_producer(schema,seed,producers,dev);weights,_=load_gates(root,seed,dev)
        for t in (t for t in templates if t['split']=='heldout'):
            name=t['id'];d=dataset('test',t);x=upload(d,slice(None),dev);n=len(x[0])
            table=model.encoder.encode_bank(schema.bank(t,'pairwise',dev));plan=device_plan(name,dev)
            # Templates can share public layouts but are tested separately.
            a={}
            for panel in ('ordinary','late_duplicate','late_union'):
                first,args=inputs(model,x,table,plan,panel,torch.arange(n,device=dev))
                with np.load(root/'traces'/f'{seed}-{name}-{panel}.npz') as z:
                    a[panel]=z['exact_trace']
                    for lane in ('exact','fixed4','blind_guard'):
                        mode,k,arm=LANES[lane]
                        q=Queue(n,plan[3],dev)
                        q.advance(args,weights[arm],mode,k,4,arm=='blind')
                        codes=status(q.state).cpu().numpy()
                        saved=checkpoint(q,args)
                        # Destroy the old executor's class, queue, materialized
                        # index, observer log and visibility, then start a new executor.
                        for v in (q.classes,q.index,q.state,q.visible,q.boundary):v.fill_(-77)
                        resumed,manifest=restore(saved)
                        for remaining in range(4,MAX_TICKS,4):
                            resumed.advance(manifest,weights[arm],mode,k,4,arm=='blind')
                        for field in ('state','visible','boundary'):
                            np.testing.assert_array_equal(getattr(resumed,field).cpu().numpy(),z[f'{lane}_48_{field}'])
                        results[f'{seed}/{name}/{panel}/{lane}']={'graphs':n,'statuses_at_4':np.bincount(codes,minlength=6).tolist()}
            # Same four features available to the blind head, identical production
            # prefix, opposite correct action solely due to the in-flight duplicate.
            hits=0
            for immediate,late in zip(a['ordinary'],a['late_duplicate']):
                ii=immediate[immediate[:,8]==1];ll=late[late[:,8]==1]
                for j in range(min(len(ii),len(ll))):
                    if not np.array_equal(ii[:j+1,:4],ll[:j+1,:4]):break
                    if ii[j,6]==2 and ll[j,6]==1:
                        hits+=1;break
            results[f'{seed}/{name}/opposite_actions']=hits
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('producers',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();a.output.write_text(json.dumps(run(a.root,a.producers),indent=1)+'\n')
