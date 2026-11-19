"""Substitute well-formed installed proofs across boundary states and endpoints."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from bake import bake,plans
from device_proof import compiled,verify
from measure import device,study,host


@torch.inference_mode()
def test(root):
    dev=device();result={};templates=study()[0];source=plans()
    for t in templates:
        name=t['id'];trace=root/'traces'/f'{name}-1703-all_requests.npz'
        if not trace.exists():continue
        p=compiled(t,source[name],dev);lib=bake(source[name]);public=lib['public']
        info={}
        with np.load(trace) as z:
            a,b,parents=[z[k][0] for k in ('a','b','parents')]
        for wrong_endpoint in (False,True):
            cases=[]
            for m,(x,y,needed,edge,offset,size) in enumerate(lib['macros']):
                read=public.index(x);origin=public.index(y)
                parent=np.flatnonzero((parents[:,0]>0)&(parents[:,8]==origin))
                if not len(parent):raise ValueError('need a genuine generated parent for the diagnostic')
                for mask in range(4):
                    for bridge in range(10):
                        q=(read+1)%6 if wrong_endpoint else read
                        valid=not wrong_endpoint and mask&needed==needed and edge in (0,bridge)
                        semantic=lib['routes'][(mask*10+bridge)*36+q*6+origin]>=0
                        cases.append((m,mask,bridge,q,origin,parent[0],valid,semantic))
            values=np.asarray(cases,dtype=np.int32);m,mask,bridge,q,origin,parent,valid,semantic=values.T
            n=len(m);claims=np.zeros((n,8,8),np.int32)
            binding={r[4]:r[:2] for r in a}
            req=np.zeros((n,4,7),np.int32)
            req[:,0]=[[*binding[l],*binding[r],3,l,r] for l,r in zip(q,origin)]
            claims[:,0]=np.column_stack((np.ones(n),parent,np.zeros(n),parents[parent,3:5],req[:,0,4],parents[parent,6:8]))
            def tensor(v):return torch.tensor(np.ascontiguousarray(v),device=dev,dtype=torch.int32)
            data=(tensor(np.repeat(a[None],n,0)),tensor(np.repeat(b[None],n,0)),
                  tensor(np.repeat(parents[None],n,0)),tensor(claims),tensor(req),tensor(np.column_stack((mask,bridge))))
            for macro in (False,True):
                stride=8*(6+(1 if macro else p['peak']));wire=np.zeros((n,stride),np.int32)
                ranges=np.zeros((n,8,2),np.int32)
                for i,mi in enumerate(m):
                    off,size=lib['macros'][mi][4:]
                    body=[mi] if macro else lib['code'][off:off+size]
                    wire[i,:6+len(body)]=[0,2,i,parent[i],0,len(body),*body]
                    ranges[i,0,1]=6+len(body)
                wire[:,0]=int(p['cfg'][0].item())
                observed=host(verify(data,p,tensor(wire),tensor(ranges),macro))[:,0,0]
                np.testing.assert_array_equal(observed,valid)
                if not wrong_endpoint:
                    missing=data[2].clone()
                    missing[...,8]=-1
                    omitted=(data[0],data[1],missing,*data[3:])
                    no_port=host(verify(omitted,p,tensor(wire),tensor(ranges),macro))[:,0,0]
                    if no_port.any():raise ValueError('accepted an omitted bound port')
                    info[f'missing_port/{"macro" if macro else "primitive"}']=dict(
                        cases=int(valid.sum()),accepted=int(no_port[valid.astype(bool)].sum()))
                info[f'{"wrong_endpoint" if wrong_endpoint else "original_endpoint"}/{"macro" if macro else "primitive"}']=dict(
                    cases=n,accepted=int(observed.sum()),rejected_despite_true_conclusion=int(((observed==0)&(semantic==1)).sum()),
                    invalid_accepted=int(((valid==0)&(observed==1)).sum()))
        result[name]=info
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args()
    (args.root/'scope-tests.json').write_text(json.dumps(test(args.root),indent=2)+'\n')
