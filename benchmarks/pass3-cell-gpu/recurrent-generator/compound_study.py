"""Source-aligned online comparison of generating children before or after verifying their parents."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import numpy as np
import torch

from capture import execute,inputs,load_catalog,read,verify
from compound_model import pair_joins
from feedback_study import bind_session


def metrics(folder):
    with np.load(folder/'compound-output.npz') as c,np.load(folder/'neural-output.npz') as z,np.load(folder/'output.npz') as g:
        claims=c['claims']; roots=z['rhs_ordinal'][:,:2];child=claims[:,:,7]
        n=len(g['rhs']);tot=g['runs'][:,1]; delivered=np.zeros(len(tot),dtype=int)
        ordinals=np.concatenate([roots[roots>0],child[child>0]])
        assert len(set(map(int,ordinals)))==len(ordinals) and (ordinals<=n).all()
        if len(ordinals):np.add.at(delivered,g['rhs'][ordinals-1,0]-1,1)
        for t,lane in zip(*np.nonzero(child)):
            parent,j,issued,row,ticket,run,bank,won,*_=claims[t,lane]
            assert roots[t,parent]==issued and g['rhs'][issued-1,0]==t+1
            assert run==g['rhs'][won-1,0] and run>t+1 and g['rhs'][won-1,3]==row and ticket>0
        status=z['verdict'][:,:2,0]
        active=claims[:,:,8]>0
        return dict(runs=len(tot),rhs=n,roots=int((roots>0).sum()),children=int((child>0).sum()),exact=n-len(ordinals),
                    nonempty=int((tot>0).sum()),full_nonempty=int(((tot>0)&(delivered==tot)).sum()),
                    roots_raw=int((status>0).sum()),root_reject=int((status==2).sum()),root_duplicate=int((status==3).sum()),
                    child_raw=int(active.sum()),statuses=np.bincount(claims[:,:,8].flatten(),minlength=7).tolist(),
                    child_attempts=int(claims[:,:,9].sum()),root_rows=(roots>0).sum(0).tolist(),
                    child_rows=(child>0).sum(0).tolist(),max_run_distance=max((int(r-t-1) for t,c in enumerate(claims) for r in c[:,5] if r),default=0))


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    donor=a.ref/'sum-bits/program.json';joins=pair_joins(read(donor))
    for case in a.cases:
        image,program,gold=inputs(a.corpus,a.ref,case)
        entries=load_catalog(image,program,donor)
        with np.load(gold/'output.npz') as z:truth={k:z[k] for k in ('runs','rhs','writes','resumes')}
        for seed in a.seeds:
            policy=read(a.training/f'train-{seed}/policy.json')
            assert list(map(list,joins))==policy['joins']
            sessions={};summary={};reference_tokens={}
            for mode in ('batch','wave','exact','batch-masked','wave-null','batch-only','wave-only'):
                folder=a.out/f'{case}-{seed}-{mode}'
                residual=not mode.endswith('only')
                cfg=None if mode=='exact' else dict(catalog=entries,rows=2,hidden=8,ranks=8,waves=2,weights=policy['roots'],
                    complete_residual=residual,intervention=3 if mode.endswith('null') else 0,
                    compound=dict(joins=joins,child=policy['child'],batch=mode.startswith('batch'),mask_parent=mode.endswith('masked')))
                timed=mode in ('batch','wave','exact')
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=cfg,
                        measure_resident=bind_session(sessions,mode) if timed else None)
                if residual:verify(folder,gold,image)
                item=metrics(folder) if cfg else dict(rhs=len(truth['rhs']))
                if cfg and residual:assert item['exact']==read(folder/'run.json')['execution_roles']['rhs_inputs_from_exact_search']
                if not residual:
                    with np.load(folder/'output.npz') as z:
                        common=min(len(z['runs']),len(truth['runs']))
                        diff=np.flatnonzero((z['runs'][:common]!=truth['runs'][:common]).any(1))
                        item['first_divergence']=int(diff[0])+1 if len(diff) else common+1
                    assert item['exact']==0
                if mode.endswith(('masked','null')):assert not item['children']
                item['aligned']=residual
                if timed:item['ms']=[]
                if timed and cfg:
                    with np.load(folder/'neural-output.npz') as z:reference_tokens[mode]=z['raw']
                summary[mode]=item
            names=list(sessions)
            for t in range(2*len(names)):
                order=names[t%len(names):]+names[:t%len(names)]
                for mode in (order if t<len(names) else order[::-1]):
                    reset,infer,buf=sessions[mode];reset();torch.mps.synchronize()
                    start=perf_counter_ns();infer();torch.mps.synchronize()
                    summary[mode]['ms'].append((perf_counter_ns()-start)/1e6)
                    st=buf['state'].cpu().tolist();assert st[7] and not st[5]
                    for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        got,want=buf[k][:st[i]].cpu().numpy(),truth[k]
                        if k=='rhs':
                            np.testing.assert_array_equal(got[:,:2],want[:,:2]);got,want=got[:,4:],want[:,4:]
                        np.testing.assert_array_equal(got,want)
                    if mode!='exact':np.testing.assert_array_equal(buf['raw_trace'][:st[11]].cpu().numpy(),reference_tokens[mode])
            for mode in names:summary[mode]['median_ms']=median(summary[mode]['ms'])
            changed=(reference_tokens['batch'][:,:,8:]!=reference_tokens['wave'][:,:,8:]).any(-1).sum(0)
            summary['changed_rows']=changed.tolist();report[f'{case}/{seed}']=summary
            (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            print(case,seed,[(m,summary[m].get('children'),round(summary[m]['median_ms'])) for m in names],flush=True)
            sessions.clear()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','training','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    with torch.inference_mode():study(p.parse_args())
