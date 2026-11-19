"""Execute one wave at a time; validate traces after finish opens the public view."""
import argparse
import json
from pathlib import Path
import time
from statistics import median
import numpy as np
import torch
from engine import ReadinessEngine, prepare_plan, DEFAULT_PLAN
from data import dataset
from audit import metrics
from predictor import ReadyPolicy
from fit import device,digest


def run(data,ix,mode,model,trace,plan,dev):
    size=len(data['events'][ix])
    engine=ReadinessEngine(size,mode=mode,device=dev,trace=trace,plan=plan)
    callback=None if model is None else model.new_stream()
    frames=[]
    for tick in range(3):
        wave=torch.as_tensor(data['events'][ix,tick],device=dev,dtype=torch.int32)
        frames.append(engine.step(wave,proposal_fn=callback))
    # End-of-stream knowledge is supplied only now.
    seal=torch.as_tensor(data['seal'][ix],device=dev,dtype=torch.bool)
    frames.append(engine.finish(seal,proposal_fn=callback))
    return engine.endpoint(),frames if trace else None,dict(engine.dispatch_counts)


def np_trace(frames):
    return {key:torch.stack([f[key] for f in frames],dim=1).cpu().numpy() for key in frames[0] if key!='tick'}


def endpoint_ok(endpoint,trace,ix):
    for key,value in endpoint.items():
        expected=trace['first_early_tick'][ix,-1]>=0 if key=='early_execution' else trace[key][ix,-1]
        np.testing.assert_array_equal(value.cpu().numpy(),expected,err_msg=key)


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args();dev=device();plan=prepare_plan()
    models={};metadata={};lanes={m:(m,None) for m in ('barrier','barrier_min','local')}
    for arm in ('keyed','blind'):
        for seed in (1703,1709):
            name=f'{arm}-{seed}';folder=args.root/name;info=json.loads((folder/'fit.json').read_text())
            assert digest(folder/'final.pt')==info['weight_sha256']
            model=ReadyPolicy(arm);model.load_state_dict(torch.load(folder/'final.pt',map_location='cpu',weights_only=True))
            models[name]=model.to(dev).eval();metadata[name]=info
            for mode in ('raw','guarded','guarded_drain'):lanes[name+'-'+mode]=mode,models[name]
    for seed in (1703,1709):
        ab=[metadata[f'{arm}-{seed}'] for arm in ('keyed','blind')]
        for key in ('init','params','batch_sha256','train_input_sha256'):assert ab[0][key]==ab[1][key]
    out=args.root/'traces';out.mkdir(exist_ok=True)
    reports={};timings={};dispatch={}
    with torch.inference_mode():
        for split in ('iid','heldout'):
            d=dataset(split);reports[split]={};timings[split]={};stored={};dispatch[split]={}
            for name,(mode,model) in lanes.items():
                endpoint,frames,_=run(d,slice(None),mode,model,True,plan,dev)
                torch.mps.synchronize();trace=np_trace(frames);endpoint_ok(endpoint,trace,slice(None))
                np.savez_compressed(out/f'{split}--{name}.npz',**trace)
                score=metrics(d,trace,mode)
                print(split,name,score['complete_graphs'],'/',score['graphs'],flush=True)
                if mode in ('barrier','local','barrier_min','guarded_drain'):
                    if score['source_contract_exact_graphs']!=len(d['events']):raise ValueError((name,score['totals']))
                saved={k:v for k,v in score.items() if k!='per_graph'}
                saved['complete_by_graph']=[bool(g['complete']) for g in score['per_graph']]
                # Record classification errors based on actually issued proposals, outside the execution.
                if model is not None:
                    truth=d['desired_ready'];prop=trace['proposal'];saved['proposal_accuracy']={
                        'tests':int(prop.size),'correct':int((truth==prop).sum()),
                        'fp':int((prop&~truth).sum()),'fn':int((~prop&truth).sum())}
                reports[split][name]=saved;stored[name]=trace
            # Timing uses complete four-variant groups to preserve the paired intervention.
            rng=np.random.default_rng(7181);groups=rng.choice(np.unique(d['group_id']),16,replace=False)
            ix=np.concatenate([np.flatnonzero(d['group_id']==g) for g in groups]);names=list(lanes)
            elapsed={n:[] for n in names};kept={n:[] for n in names}
            for name,(mode,m) in lanes.items():
                for i in ix[:4]:run(d,slice(i,i+1),mode,m,False,plan,dev);torch.mps.synchronize()
            for j,i in enumerate(ix):
                for name in names[j%len(names):]+names[:j%len(names)]:
                    mode,m=lanes[name];start=time.perf_counter_ns()
                    endpoint,_,counts=run(d,slice(i,i+1),mode,m,False,plan,dev);torch.mps.synchronize()
                    elapsed[name].append((time.perf_counter_ns()-start)/1.e6)
                    kept[name].append(endpoint);dispatch[split][name]=counts
            for name in names:
                for i,endpoint in zip(ix,kept[name]):endpoint_ok(endpoint,stored[name],slice(i,i+1))
                times=elapsed[name];wins=sum(reports[split][name]['complete_by_graph'][i] for i in ix)
                timings[split][name]=dict(samples_ms=times,indices=ix.tolist(),median_ms=median(times),
                    correct=wins,graphs=len(ix),correct_per_second=1000*wins/sum(times))
    result=dict(panels=reports,timings=timings,dispatch=dispatch,fits=metadata,
                plan_sha256=digest(DEFAULT_PLAN),evaluator_sha256=digest(__file__),
                scope='Private RHS computation on monotone single-value facts; public results at finish only; MPS timing from engine creation, per-wave upload to final synchronized endpoint.')
    (args.root/'results.json').write_text(json.dumps(result,separators=(',',':'))+'\n')

if __name__=='__main__':main()
