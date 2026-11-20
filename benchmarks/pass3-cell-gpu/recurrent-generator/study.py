"""Paired actor x verifier ablation in the running Pass 3 engine, with a latent intervention."""
import argparse,json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import numpy as np
import torch
from capture import read,inputs,load_catalog,verify,execute
from model import Actor,HIDDEN,ROWS

def parity(capture,net,raw,intervention):
    torch.set_num_threads(1)
    with np.load(capture/'neural-inputs.npz') as z:features=torch.tensor(z['features'])
    prev=torch.zeros(1,ROWS,HIDDEN+4);expected=(1,ROWS,HIDDEN+4)
    largest=0.;discrete=0
    with torch.no_grad():
        for i,frame in enumerate(features):
            _,pred=net.step(frame[None],prev,intervention)
            value=torch.tensor(raw[i])[None]
            if value.shape!=expected:raise ValueError('token shape')
            if intervention=='all-null':
                # The force-abstain control is tested by the verifier itself.
                assert not value[:,:,HIDDEN:].any()
            else:
                discrete+=int((value[:,:,HIDDEN:]!=pred[:,:,HIDDEN:]).any(dim=-1).sum())
                largest=max(largest,float((value[:,:,:HIDDEN]-pred[:,:,:HIDDEN]).abs().max()))
            prev=value  # Check the exact predecessor actually produced by Metal.
    return dict(discrete_differences=discrete,largest_latent_difference=largest)

def record(folder):
    j=read(folder/'run.json')
    with np.load(folder/'neural-output.npz') as f,np.load(folder/'output.npz') as z:
        raw=f['raw'].copy();status=f['verdict'][:,:,0];won=f['committed']
        counts=z['runs'][:,1]
        assert np.array_equal(raw[:,:,-1]!=0,status!=0) and np.all((won==0)|(status==1))
        roles=j['execution_roles']
        assert roles['rhs_inputs_from_recurrent_neural_proposals']==int(won.sum())
        stats=dict(raw=int((status>0).sum()),duplicate=int((status==3).sum()),accepted=int((status==1).sum()),
            rejected=int((status==2).sum()),rows_won=won.sum(0).tolist(),won=int(won.sum()),exact_fallback=int(counts.sum()-won.sum()),
            rhs=int(counts.sum()),nonempty=int((counts>0).sum()),whole_nonempty=int(((counts>0)&(counts==won.sum(1))).sum()),
            nonempty_both=int((won.sum(1)==2).sum()),runs=len(counts),semantic_exact=True)
        return stats,raw

def main(a):
    a.out.mkdir(parents=True,exist_ok=False);reports={}
    variants={'exact':None,'intact':(0,True,False),'zero-latent':(1,True,False),'swap-latent':(2,True,False),
              'positive-only':(0,False,False),'zero-positive':(1,False,False),'all-null':(3,True,False),'shadow':(0,False,True)}
    for n in a.cases:
        image,p,gold=inputs(a.corpus,a.ref,n)
        contracts=load_catalog(image,p,a.ref/'sum-bits/program.json')
        for seed in a.seeds:
            study={};sessions={};raws={}
            trained=a.capture/f'train-{seed}';weights=read(trained/'actor.json')
            net=Actor();net.load_state_dict(torch.load(trained/'actor.pt',map_location='cpu',weights_only=True));net.eval()
            for name,v in variants.items():
                cfg=None if v is None else dict(catalog=contracts,weights=weights['weights'],hidden=weights['hidden'],ranks=weights['ranks'],
                                                 rows=weights['rows'],intervention=v[0],close=v[1],shadow=v[2])
                folder=a.out/f'{n}-{seed}-{name}'
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=cfg,count_work=True)
                verify(folder,gold,image)
                if cfg:
                    stats,raw=record(folder)
                    stats['work']=read(folder/'run.json')['neural_work_counts']
                    test='zero-latent' if v[0]==1 else 'swap-latent' if v[0]==2 else 'all-null' if v[0]==3 else 'intact'
                    stats['actor_parity']=parity(a.capture/n,net,raw,test)
                    assert stats['actor_parity']['discrete_differences']==0 and stats['actor_parity']['largest_latent_difference']<.002,(n,seed,name,stats['actor_parity'])
                    raws[name]=raw
                else:stats={'semantic_exact':True,'roles':read(folder/'run.json')['execution_roles']}
                study[name]=stats
            r=raws['intact']
            for name,raw in raws.items():
                study[name]['changed_discrete_vs_intact']=int(np.any(raw[:,:,HIDDEN:]!=r[:,:,HIDDEN:],axis=-1).sum())
            for a1,b1 in [('intact','positive-only'),('intact','shadow'),('zero-latent','zero-positive')]:
                np.testing.assert_array_equal(raws[a1],raws[b1])
            assert study['all-null']['raw']==0 and study['shadow']['won']==0
            for yes,no in [('intact','positive-only'),('zero-latent','zero-positive')]:
                u,v=study[yes]['work'],study[no]['work']
                assert u['exact_seeds_skipped']==study[yes]['accepted'] and v['exact_seeds_skipped']==0
                assert 0<=v['remaining_route_steps']-u['remaining_route_steps']<=u['verified_steps']
                assert 0<=v['remaining_route_point_reads']-u['remaining_route_point_reads']<=u['verifier_point_reads']
            # Pair the two actor histories and the two verifier strategies. A
            # common exact baseline isolates the overhead of neural generation.
            timed=['exact','intact','positive-only','zero-latent','zero-positive']
            with np.load(gold/'output.npz') as z:truth={k:z[k] for k in ('runs','rhs','writes','resumes')}
            for name in timed:
                v=variants[name]
                cfg=None if v is None else dict(catalog=contracts,weights=weights['weights'],hidden=weights['hidden'],ranks=weights['ranks'],
                                                 rows=weights['rows'],intervention=v[0],close=v[1],shadow=v[2])
                def bind(infer,buf,*unused):
                    sources={k:buf[k].clone() for k in ('state','meta','head','dyn','wm')}
                    def reset():
                        for k,t in sources.items():buf[k].copy_(t)
                        for k in ('regs','count','rhs','runs','writes','resumes','frontier','raw_trace','verdict'):
                            if k in buf:buf[k].zero_()
                    sessions[name]=reset,infer,buf
                folder=a.out/f'{n}-{seed}-{name}-resident'
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=cfg,measure_resident=bind)
                verify(folder,gold,image);study[name]['ms']=[]
            for trial in range(2*len(timed)):
                order=timed[trial%len(timed):]+timed[:trial%len(timed)]
                for name in order if trial<len(timed) else order[::-1]:
                    reset,infer,buf=sessions[name];reset();torch.mps.synchronize()
                    begin=perf_counter_ns();infer();torch.mps.synchronize();ms=(perf_counter_ns()-begin)/1e6
                    st=buf['state'].cpu().tolist();assert st[7] and not st[5]
                    for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        got=buf[k][:st[i]].cpu().numpy();want=truth[k]
                        if k=='rhs':
                            np.testing.assert_array_equal(got[:,:2],want[:,:2]);got,want=got[:,4:],want[:,4:]
                        np.testing.assert_array_equal(got,want)
                    if name!='exact':np.testing.assert_array_equal(buf['raw_trace'][:st[11]].cpu().numpy(),raws[name])
                    study[name]['ms'].append(ms)
            for name in timed:study[name]['median_ms']=median(study[name]['ms'])
            reports[f'{n}/{seed}']=study;(a.out/'results.json').write_text(json.dumps(reports,indent=1)+'\n')
            print(n,seed,[(k,study[k].get('won'),round(study[k]['median_ms'])) for k in timed],flush=True)
            sessions.clear()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():main(p.parse_args())
