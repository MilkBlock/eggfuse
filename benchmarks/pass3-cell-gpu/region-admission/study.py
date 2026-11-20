"""Run full, bounded static, learned and hindsight directories on independent families."""
import argparse,hashlib,json
from pathlib import Path
from time import perf_counter_ns
from statistics import median
import numpy as np
import torch
from fit import Trace,fit
from capture import policy
from collect import read
from device import execute_case,files

@torch.inference_mode()
def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    cases=read(a.corpus/'collection.json');train=[n for n,v in cases.items() if v['split']=='train']
    static,learned=fit([Trace(a.capture/n) for n in train],a.budget)
    frozen=a.out/'policy.json'
    frozen.write_text(json.dumps(dict(train=train,static=static,learned=learned),indent=2)+'\n')
    model_sha=hashlib.sha256(frozen.read_bytes()).hexdigest();report={}
    for n,case in cases.items():
        if n in train:continue
        assert hashlib.sha256(frozen.read_bytes()).hexdigest()==model_sha
        t=Trace(a.capture/n);truth=t.oracle(a.budget)
        masks=np.zeros((2048//32+1,16),np.uint32)
        for i,rows in enumerate(truth):
            for row in rows:masks[i,row//32]|=np.uint32(1<<(row%32))
        arms={'full':{'full':True},'static':static,'learned':learned,'hindsight':dict(learned,oracle=masks.flatten().tolist())}
        sessions={};results={}
        _,_,gold=files(a.corpus,a.reference,n)
        with np.load(gold/'output.npz') as z:expected={k:z[k] for k in ('runs','writes','rhs','resumes')}
        for k,arm in arms.items():
            counted=a.out/f'{n}-{k}-counts'
            r=execute_case(a.corpus,a.reference,a.weights,n,counted,region=arm,count=True)
            info=dict(inspections=r['state'][55],notify_word_visits=r['state'][74],exact=True,runs=r['completed'])
            if k!='full':
                selected=truth if k=='hindsight' else t.select(arm)
                with np.load(counted/'selected.npz') as f:
                    observed=[{32*j+bit for j,word in enumerate(window) for bit in range(32) if int(word)&(1<<bit)}
                              for window in f['words'][:len(selected)]]
                assert observed==selected,(n,k,[(i,v,observed[i]) for i,v in enumerate(selected) if observed[i]!=v][:1])
                costs=t.work(selected)
                whole=read(a.capture/n/'run.json')['state'][55]
                assert costs['clean_rows_saved']==whole-info['inspections'],(n,k,costs,whole,info)
                info['price']=costs;info['maintenance']=r['region']['counters'][1:]
            def retain(infer,buf,*_):
                seed={v:buf[v].clone() for v in ('state','regs','meta','head','dyn','wm')}
                def reset():
                    for v,val in seed.items():buf[v].copy_(val)
                    for v in ('count','rhs','writes','runs','resumes'):buf[v].zero_()
                sessions[k]=reset,infer,buf
            ordinary=execute_case(a.corpus,a.reference,a.weights,n,a.out/f'{n}-{k}',region=arm,count=False,resident=retain)
            info['index_bytes']=ordinary['region']['index_bytes'] if k!='full' else 4*(16384//32)*(16384+read(files(a.corpus,a.reference,n)[0]/'device.json')['layout']['NSYMBOLS']+4)
            info['samples_ms']=[];results[k]=info
        for i in range(8):
            order=list(arms);order=order[i%4:]+order[:i%4]
            for k in order if i<4 else order[::-1]:
                reset,infer,buf=sessions[k];reset();torch.mps.synchronize()
                start=perf_counter_ns();infer();torch.mps.synchronize()
                elapsed=(perf_counter_ns()-start)/1e6
                st=buf['state'].cpu().tolist();assert not st[5] and st[7]
                for name,j in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                    v=buf[name][:st[j]].cpu().numpy();w=expected[name]
                    if name=='rhs':
                        np.testing.assert_array_equal(v[:,:2],w[:,:2]);v,w=v[:,4:],w[:,4:]
                    np.testing.assert_array_equal(v,w)
                results[k]['samples_ms'].append(elapsed)
        for item in results.values():item['median_ms']=median(item['samples_ms'])
        report[n]=dict(program=case['program'],policy_sha256=model_sha,arms=results)
        (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(n,{k:(round(v['median_ms']),v['inspections']) for k,v in results.items()},flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','reference','weights','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--budget',type=int,default=32)
    main(p.parse_args())
