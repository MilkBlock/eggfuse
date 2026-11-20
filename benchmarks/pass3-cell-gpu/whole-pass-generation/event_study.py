"""Fixed neural forest and final sweep, dense scheduling versus on-publication activation."""
import argparse,json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import numpy as np
import torch
from adapter import specialize,run
from study import open_generator,inputs,packet,verify,audit


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    for case in a.cases:
        image,program,source=inputs(a.corpus,a.ref,case);p=packet(image,program)
        for seed in a.seeds:
            ck=torch.load(a.weights/f'policy-{seed}.pt',weights_only=True)
            sessions={};report={}
            for arm in ('exact','dense','events','proof-only'):
                emit,saved=open_generator(p,ck,'proof-only' if arm=='proof-only' else 'learned')
                fn=run.execute if arm=='exact' else specialize(p,emit,True,arm in ('events','proof-only'))
                if arm!='exact':
                    folder=a.out/f'{case}-{seed}-{arm}-work'
                    fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,count_work=True)
                    verify(folder,source,image)
                    raw=saved[0].cpu().numpy();stats=audit(folder,source,p,raw,True)
                    with np.load(folder/'forest.npz') as z:
                        visited=int(z['visits']);winners=z['children'][:,2].copy();roots=z['roots'][:,2].copy()
                    if arm=='dense':recorded=(raw.copy(),winners,roots)
                    elif arm=='events':
                        for x,y in zip((raw,winners,roots),recorded):np.testing.assert_array_equal(x,y)
                    else:
                        np.testing.assert_array_equal(raw[:,:5],recorded[0][:,:5])
                        assert stats['projection_rhs']==stats['child_winners']
                        assert not (winners[raw[:,5]<=0]>0).any()
                    report[arm]=dict(winners=stats['child_winners'],visits=visited,attempts=stats['point_route_attempts'],
                                     exact_residual=stats['exact_residual'],declined_missing_suffix=int((raw[:,5]==-2).sum()),ms=[])
                else:report[arm]=dict(ms=[])
                def bind(infer,buf,*_):
                    original={k:buf[k].clone() for k in ('state','meta','head','dyn','wm')}
                    def reset():
                        for k,v in original.items():buf[k].copy_(v)
                        for k in ('regs','count','rhs','runs','writes','resumes'):buf[k].zero_()
                    sessions[arm]=reset,infer,buf
                trial=a.out/f'{case}-{seed}-{arm}-time'
                fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,trial,measure_resident=bind)
                verify(trial,source,image)
            order=list(sessions)
            with np.load(source/'output.npz') as z:gold={k:z[k].copy() for k in ('runs','writes','resumes','rhs')}
            for trial in range(2*len(order)):
                seq=order[trial%len(order):]+order[:trial%len(order)]
                for arm in seq if trial<len(order) else seq[::-1]:
                    reset,infer,buf=sessions[arm];reset();torch.mps.synchronize()
                    tick=perf_counter_ns();infer();torch.mps.synchronize()
                    report[arm]['ms'].append((perf_counter_ns()-tick)/1e6)
                    st=buf['state'].cpu().tolist()
                    assert st[7] and not st[5]
                    for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        h,w=buf[k][:st[i]].cpu().numpy(),gold[k]
                        if k=='rhs':np.testing.assert_array_equal(h[:,:2],w[:,:2]);h,w=h[:,4:],w[:,4:]
                        np.testing.assert_array_equal(h,w)
            for row in report.values():row['median_ms']=median(row['ms'])
            folder=a.out/f'{case}-{seed}-proof-only-no-residual'
            emit,saved=open_generator(p,ck,'proof-only')
            specialize(p,emit,False,True)(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder)
            stats=audit(folder,source,p,saved[0].cpu().numpy(),False)
            assert stats['exact_residual']==0 and stats['projection_rhs']==stats['child_winners']
            report['proof-only-no-residual']=dict(static_roots=stats['static_roots'],child_winners=stats['child_winners'],
                first_divergence=stats['first_divergence'],actual_rhs=stats['actual_rhs'])
            # Standalone diagnostic. Synchronize each whole-forest forward and global sweep, including MPS launch.
            emit,_=open_generator(p,ck,'learned')
            emit();torch.mps.synchronize();samples=[]
            for _ in range(16):
                tick=perf_counter_ns();roots,tokens,latent=emit();torch.mps.synchronize()
                samples.append((perf_counter_ns()-tick)/1e6)
            report['generation_and_global_sweep']=dict(ms=samples,median_ms=median(samples),
                static_root_count=len(roots),candidate_slots=len(tokens),active_children=int(tokens[:,0].sum().item()),
                emitted_tensor_bytes=sum(t.numel()*t.element_size() for t in (roots,tokens,latent)))
            summary[f'{case}/{seed}']=report
            (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
            print(case,seed,[(k,v.get('visits'),round(v['median_ms'])) for k,v in report.items() if 'median_ms' in v],flush=True)
            sessions.clear()


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','ref','reader','weights','out'):ap.add_argument(name,type=Path)
    ap.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    ap.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    with torch.inference_mode():study(ap.parse_args())
