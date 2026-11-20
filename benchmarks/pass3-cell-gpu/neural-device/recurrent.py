"""Real per-Run CPU/Metal recurrent generation with identical GPU observations and exact verifier."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'recurrent-generator'))
from capture import execute,inputs,load_catalog,read,verify
from compound_model import CompoundActor,pair_joins
from compound_study import metrics
from feedback_study import bind_session


class HostActor:
    def __init__(self,weights,entries,joins):
        self.net=CompoundActor(joins)
        self.net.load_state_dict(torch.load(weights,weights_only=True));self.net.eval()
        for j,(_,_,_,right) in enumerate(joins):
            if entries[right][0]<0:self.net.row_score[:,j]=-1e6
        self.reply=torch.zeros(1,2,4,dtype=torch.long)
        self.reset()

    def reset(self):
        self.previous=torch.zeros(1,2,12)

    def emit(self,observation,run):
        _,roots=self.net.root.step(observation,self.previous)
        _,self.previous,_=self.net.propose_children(roots,self.reply,False,torch.tensor([run]))
        return torch.cat([roots,self.previous],1)[0]


def study(a):
    torch.set_num_interop_threads(1);torch.set_num_threads(1)
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        image,program,gold=inputs(a.corpus,a.ref,case);donor=a.ref/'sum-bits/program.json'
        entries=load_catalog(image,program,donor);joins=pair_joins(read(donor))
        for seed in a.seeds:
            ck=a.weights/f'train-{seed}';weights=read(ck/'policy.json')
            sessions={};summary={};raws={}
            for name,threads in [('metal',1),('metal-readback',1),('cpu-1',1),('cpu-4',4)]:
                torch.set_num_threads(threads)
                device_cfg=dict(joins=joins,child=weights['child'],batch=True,host_control=name!='metal')
                if name.startswith('cpu'):
                    device_cfg['host_actor']=HostActor(ck/'actor.pt',entries,joins)
                cfg=dict(catalog=entries,weights=weights['roots'],rows=2,ranks=8,hidden=8,waves=2,compound=device_cfg)
                dest=a.out/f'{case}-{seed}-{name}'
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,neural=cfg,measure_resident=bind_session(sessions,name))
                verify(dest,gold,image);item=metrics(dest)
                with np.load(dest/'neural-output.npz') as z,np.load(dest/'compound-output.npz') as c:
                    raw=z['raw'];claims=c['claims'];ordinals=z['rhs_ordinal']
                    if name=='metal':base=raw;origin=ordinals;children=claims
                    item['changed_rows']=int((raw[:,:,8:]!=base[:,:,8:]).any(-1).sum())
                    item['max_latent_difference']=float(np.abs(raw[:,:,:8]-base[:,:,:8]).max())
                    item['changed_root_ordinals']=int((ordinals!=origin).sum())
                    item['changed_child_records']=int((claims!=children).any(-1).sum())
                    raws[name]=raw
                item.update(ms=[],threads=threads,logical_bytes_read=(0 if name=='metal' else 256*8*4*(item['runs']+1)),
                            logical_bytes_uploaded=4*12*4*item['runs'] if name.startswith('cpu') else 0)
                summary[name]=item
            names=list(summary)
            for trial in range(2*len(names)):
                order=names[trial%len(names):]+names[:trial%len(names)]
                for name in order if trial<len(names) else order[::-1]:
                    torch.set_num_threads(summary[name]['threads']);reset,infer,buf=sessions[name]
                    reset();torch.mps.synchronize();start=perf_counter_ns()
                    infer();torch.mps.synchronize();summary[name]['ms'].append((perf_counter_ns()-start)/1e6)
                    st=buf['state'].cpu().tolist();assert st[7] and not st[5] and st[9]==summary[name]['rhs']
                    np.testing.assert_array_equal(buf['raw_trace'][:st[11]].cpu().numpy(),raws[name])
            for item in summary.values():item['median_ms']=median(item['ms'])
            results[f'{case}/{seed}']=summary
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,seed,[(n,round(v['median_ms']),v['changed_rows']) for n,v in summary.items()],flush=True)
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():study(p.parse_args())
