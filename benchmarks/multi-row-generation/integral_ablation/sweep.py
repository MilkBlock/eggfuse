"""Compare all 36 GPU reads for each actual three-ruleset Rust run."""
import argparse
import hashlib
from itertools import product
import json
from pathlib import Path

import numpy as np
import torch
from integral import dataset,study,device,load_producer,upload,device_plan,ingress,run


@torch.inference_mode()
def sweep(producers,native,out):
    records=json.loads(native.read_text())['results']
    dev=device();templates,_,_,schema=study();m=load_producer(schema,1703,producers,dev)
    results={}
    for t in templates:
        rid='r'+t['id'].split('-')[1]
        if not any(k.startswith(rid+'-') for k in records):continue
        base=dataset('test',t,8);public=list(product((0,1),t['public_ports']))
        certificate=t['certificates'][0];p,q=(certificate[k] for k in ('left_port','right_port'))
        other,=set(t['public_ports'])-{p,q}
        ports={'p':p,'q':q,'r':other}
        names=[k for k in records if k.startswith(rid+'-')]
        assert len(names)==9
        n=9*len(names);idx=np.full(n,6)
        d={k:v[idx].copy() if isinstance(v,np.ndarray) else v for k,v in base.items()}
        handles={(int(row[0]),int(port)):int(row[1]) for row,port in zip(d['a'][0],d['a_port'][0])}
        pairs=list(product(public,repeat=2))
        for g,name in enumerate(names):
            lhs,rhs=(ports[ch] for ch in name.split('-')[-1])
            for j in range(9):
                i=g*9+j;d['external'][i]=[1,0,handles[0,lhs],1,handles[1,rhs]];d['external_ports'][i]=[lhs,rhs]
                for slot,((owner,l),(peer,r)) in enumerate(pairs[4*j:4*j+4]):
                    d['requests'][i,slot]=[owner,handles[owner,l],peer,handles[peer,r],slot]
                    d['request_ports'][i,slot]=[l,r]
        x=upload(d,slice(None),dev);table=m.encoder.encode_bank(schema.bank(t,'pairwise',dev));plan=device_plan(t['id'],dev)
        for mode in ('source','primary','integral','learned_integral','stable_integral'):
            _,inputs,admit=ingress(m,x,table,mode);_,frames=run(x,plan,inputs,admit,mode,True)
            stages=[s['pub'].cpu().numpy().reshape(n,4,4,14) for s in frames]
            for stage,rows in enumerate(stages):
                flags=(rows[...,0]>=0)
                np.testing.assert_array_equal(flags,np.broadcast_to(np.asarray([0,1,1,2])<=stage,flags.shape))
            for g,name in enumerate(names):
                rows=stages[2][g*9:g*9+9,:,3].reshape(36,14)
                packed=sorted((16*oo+l,16*pp+r,int(row[7]),int(row[8])) for ((oo,l),(pp,r)),row in zip(pairs,rows))
                sha=hashlib.sha256(json.dumps(packed).encode()).hexdigest()
                if sha!=records[name]['final_signature']:raise ValueError((name,mode))
                old=stages[1][g*9:g*9+9,:,2,7].reshape(36)
                np.testing.assert_array_equal(old,rows[:,7])
            results[t['id']+'/'+mode]=dict(cases=len(names),full_histories=36*len(names))
    out.write_text(json.dumps(results,indent=1)+'\n')
    print('GPU original and private schedules reproduced',len(records),'actual Rust boundary-history signatures per mode')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('producers','native','out'):p.add_argument(key,type=Path)
    a=p.parse_args();sweep(a.producers,a.native,a.out)
