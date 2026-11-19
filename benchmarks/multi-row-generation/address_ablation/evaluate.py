"""Run frozen models, score actual GPU witnesses and audit physically remapped predictions."""
import argparse
import json
from pathlib import Path
import statistics
import time
import numpy as np
import torch
from data import audit
from model import AddressModel
from study import ARMS, SEEDS, panels, digest, input_digest
from fit import device

OUTPUTS = ('ptr1','ptr2','pair_origin','pair_value','pair_latent','result_value')
DISCRETE = ('ptr1','ptr2','pair_origin','pair_value','result_value')


def transfer(d, ix, dev):
    return tuple(torch.as_tensor(d[k][ix], device=dev) for k in ('make_ref','finish_ref','value'))


def run(model, coords, d, ix, length, ports, dev):
    out=model(coords,*transfer(d,ix,dev),length,ports)
    return {key:out[key] for key in OUTPUTS}


def collect(parts):
    return {k:np.concatenate([x[k].detach().cpu().numpy() for x in parts]) for k in OUTPUTS}


def subset(d,ix):return {k:(v if k=='coords' else v[ix]) for k,v in d.items()}


def assess(d,out):
    if not np.isfinite(out['pair_latent']).all():raise ValueError('nonfinite generated Pair latent')
    r=audit(d,*(out[k] for k in DISCRETE))
    g=np.arange(len(out['ptr1']))[:,None]
    for label,p,truth,want in [('run1',out['ptr1'],d['target1'],d['make_ref']),
                                ('run2',out['ptr2'],d['target2'],d['finish_ref'])]:
        right=(p==truth)
        if label=='run2':right=right&(out['ptr1'][g,truth]==d['target1'][g,truth])
        for class_name,mask in [('new_ordinal',want[...,2]>=3),('old_ordinal',want[...,2]<3)]:
            r[label][class_name+'_obligations']=int(mask.sum())
            r[label][class_name+'_correct']=int((mask&right).sum())
    return r


def mapped(old,new,mapping,shape):
    ids=np.arange(len(mapping))[:,None]
    checks={}
    for rule in ('ptr1','ptr2'):
        ok=new[rule][ids,mapping]==mapping[ids,old[rule]]
        checks[rule+'_equal']=int(ok.sum());checks[rule+'_exact_graphs']=int(ok.all(-1).sum())
    _,l,p=shape
    origins=new['pair_origin']
    new_flat=(origins[...,0]*l+origins[...,1])*p+origins[...,2]
    # Each actual old Pair origin equals its checked first-stage pointer.
    ok=new_flat[ids,mapping]==mapping[ids,old['ptr1']]
    checks['origins_equal']=int(ok.sum())
    for key in ('pair_value','result_value'):
        checks[key+'_equal']=int((new[key][ids,mapping]==old[key]).sum())
    return dict(graphs=len(mapping),slots=int(mapping.size),**checks)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);a=parser.parse_args();dev=device()
    suite,pairs=panels();models={};fits={};inits={}
    for arm in ARMS:
        for seed in SEEDS:
            name=f'{arm}-{seed}';folder=a.root/name;meta=json.loads((folder/'fit.json').read_text())
            assert digest(folder/'final.pt')==meta['weight']
            key=(meta['params'],meta['init'],meta['train_hashes'],meta['data_order'])
            if seed in inits:assert key==inits[seed],name
            inits[seed]=key
            m=AddressModel(arm);m.load_state_dict(torch.load(folder/'final.pt',map_location='cpu',weights_only=True))
            models[name]=m.to(dev).eval();fits[name]=meta
    traces=a.root/'traces';traces.mkdir(exist_ok=True)
    reports={};timings={};mapping_checks={}
    with torch.inference_mode():
        for panel,(r,l,p,d) in suite.items():
            coords=torch.as_tensor(d['coords'],device=dev);n=len(d['coords'])
            reports[panel]={};timings[panel]={};mapping_checks[panel]={}
            for name,m in models.items():
                parts=[run(m,coords,d,slice(i,i+8),l,p,dev) for i in range(0,len(d['value']),8)]
                torch.mps.synchronize();out=collect(parts);del parts
                reports[panel][name]=assess(d,out)
                np.savez_compressed(traces/f'{panel}-{name}.npz',**{k:out[k] for k in DISCRETE})
                if panel in pairs:
                    origin,permutation=pairs[panel]
                    with np.load(traces/f'{origin}-{name}.npz') as base:
                        mapping_checks[panel][name]=mapped(base,out,permutation,(r,l,p))
            # Rotate backend execution order across identical raw inputs; all new
            # Pair tensors incl. their continuous component are materialized on MPS.
            sampled=np.random.default_rng(95117).choice(len(d['value']),32,replace=False)
            selected=subset(d,sampled);names=list(models)
            times={name:[] for name in names};kept={name:[] for name in names}
            for name,m in models.items():
                for i in range(4):run(m,coords,selected,slice(i,i+1),l,p,dev);torch.mps.synchronize()
            for i in range(len(sampled)):
                start_name=i%len(names)
                for name in names[start_name:]+names[:start_name]:
                    start=time.perf_counter_ns();x=run(models[name],coords,selected,slice(i,i+1),l,p,dev);torch.mps.synchronize()
                    times[name].append((time.perf_counter_ns()-start)/1e6);kept[name].append(x)
            for name in names:
                stats=assess(selected,collect(kept[name]))
                timings[panel][name]=dict(samples_ms=times[name],indices=sampled.tolist(),
                    median_ms=statistics.median(times[name]),exact=stats['whole_graphs'],
                    exact_graphs_per_second=stats['whole_graphs']*1000/sum(times[name]))
            print(panel,{k:v['whole_graphs'] for k,v in reports[panel].items()},flush=True)
    result=dict(fits=fits,panel_hashes={k:input_digest(d) for k,(_,_,_,d) in suite.items()},
                shapes={k:list(v[:3]) for k,v in suite.items()},reports=reports,timings=timings,relayout=mapping_checks)
    (a.root/'results.json').write_text(json.dumps(result,separators=(',',':'))+'\n')

if __name__=='__main__':main()
