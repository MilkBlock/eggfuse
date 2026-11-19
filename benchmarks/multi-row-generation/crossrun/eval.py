"""Measure the device dataflow and independently audit its materialized tokens."""
from pathlib import Path
import argparse
import json
import itertools
import time
import statistics
import sys
import hashlib
import numpy as np
import mlx.core as mx
from cross_model import CrossRun, BASE, decode, projection_recipe
sys.path.insert(0, str(BASE/'data'))
from crossrun_data import dataset
from crossrun_audit import audit, audit_twins

SPLITS = ('iid','left_collision','right_collision')
MASKS = ('none','parents','parents_latent')


def device(model,mask):
    def forward(a,b,req):
        stages,token = model(a,b,req,mask)
        first,second = decode(stages)
        finite = mx.all(mx.isfinite(token),axis=(1,2))
        for stage in stages:
            for logits in stage:
                finite = finite & mx.all(mx.isfinite(logits),axis=(1,2))
        return first,second,token,finite
    return mx.compile(forward)


def check_token(first,token):
    decisions = [first['active'], *first['pointers'].transpose(2,0,1), *first['fields'].transpose(2,0,1)]
    offset = 64
    for width,values in zip((2,4,4,8,4,4),decisions):
        np.testing.assert_array_equal(token[...,offset:offset+width],np.eye(width)[values]);offset += width


def supplied(data,first,per_graph):
    eligible=passed=0
    for g,graph in enumerate(per_graph):
        if not graph['nonempty']:continue
        wanted={tuple(row[1:3]) for row in data['target2'][g] if row[0]}
        present=set()
        for slot in np.flatnonzero(first['active'][g]):
            i,j=first['pointers'][g,slot]
            key,x=data['a'][g,i];other,y=data['b'][g,j]
            if key==other and tuple(first['fields'][g,slot])==(key,x,y):present.add((i,j))
        if wanted<=present:
            eligible+=1;passed+=graph['complete']
    return dict(eligible=eligible,complete=passed)


def inspect(data,first,second,twins=False):
    result=audit(data['a'],data['b'],data['requests'],first,second)
    result['supplied']=supplied(data,first,result['run2']['per_graph'])
    if twins:result['twins']=audit_twins(data['a'],data['b'],data['requests'],first,second)
    return result


def merge(chunks):
    return {key:np.concatenate([c[key] for c in chunks]) for key in chunks[0]}


def data_gpu(d,index):return tuple(mx.array(d[k][index]) for k in ('a','b','requests'))


def summarize(result):
    return {k:({name:value for name,value in v.items() if name!='per_graph'} if isinstance(v,dict) else v) for k,v in result.items()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);plan_path=BASE/'compiler/plan.json';plan=projection_recipe(plan_path)
    functions={};initials={};meta={};fitted={}
    for arm,seed in itertools.product(('learned','static','aux'),(1703,1709)):
        name=f'{arm}-{seed}';fit=args.root/name;info=json.loads((fit/'fit.json').read_text());meta[name]=info
        weights=fit/'model.safetensors'
        assert hashlib.sha256(weights.read_bytes()).hexdigest()==info['model_sha256']
        assert hashlib.sha256(plan_path.read_bytes()).hexdigest()==info['plan_sha256']
        if seed in initials:assert initials[seed]==info['initial_sha256']
        initials[seed]=info['initial_sha256']
        m=CrossRun(arm,plan);m.load_weights(str(weights));mx.eval(m.parameters());fitted[name]=m
        for mask in MASKS:functions[name,mask]=device(m,mask)
    panels={k:dataset(k) for k in SPLITS};reports={};timings={};pairs={};outdir=args.root/'traces';outdir.mkdir(exist_ok=True)
    # No oracle calls between either stage or the generation of intervention outputs.
    for split,d in panels.items():
        for (name,mask),fn in functions.items():
            chunks=[[],[]];tokens=[]
            for start in range(0,len(d['a']),64):
                out=fn(*data_gpu(d,slice(start,start+64)));mx.eval(out)
                for stage,chunk in zip(out[:2],chunks):chunk.append({k:np.array(v) for k,v in stage.items()})
                tokens.append(np.array(out[2]));assert np.asarray(out[3]).all()
            first,second=map(merge,chunks);token=np.concatenate(tokens);check_token(first,token)
            np.savez_compressed(outdir/f'{name}-{split}-{mask}.npz',**{'one_'+k:v for k,v in first.items()},**{'two_'+k:v for k,v in second.items()},token=token)
    for split,d in panels.items():
        for name in fitted:
            base=None
            for mask in MASKS:
                label=f'{name}-{split}-{mask}'
                with np.load(outdir/(label+'.npz')) as z:
                    first={k:z['one_'+k] for k in ('active','pointers','fields')};second={k:z['two_'+k] for k in first}
                    if base is None:base=z['token']
                    else:np.testing.assert_array_equal(base,z['token'])
                    r=inspect(d,first,second,split.endswith('collision'));reports[label]=summarize(r)
                    pairs[label]=[g['complete'] for g in r['run2']['per_graph']]
        # Separate batch-one measurements. Every invocation uploads raw inputs and synchronizes both stages.
        ix=np.random.default_rng(81911).choice(len(d['a']),32,replace=False);selected={k:v[ix] for k,v in d.items()}
        lanes=list(functions);samples={lane:[] for lane in lanes};outputs={lane:[] for lane in lanes}
        for lane in lanes:
            for i in range(3):mx.eval(functions[lane](*data_gpu(selected,slice(i,i+1))))
        for i in range(len(ix)):
            for lane in lanes[i%len(lanes):]+lanes[:i%len(lanes)]:
                start=time.perf_counter_ns();out=functions[lane](*data_gpu(selected,slice(i,i+1)));mx.eval(out)
                samples[lane].append((time.perf_counter_ns()-start)/1.e6);outputs[lane].append(out)
        for (name,mask),sample in samples.items():
            lane=(name,mask);stages=[merge([{k:np.asarray(v) for k,v in run[s].items()} for run in outputs[lane]]) for s in (0,1)]
            for run in outputs[lane]:assert np.asarray(run[3]).all()
            check_token(stages[0],np.concatenate([np.asarray(x[2]) for x in outputs[lane]]))
            r=inspect(selected,*stages);timings[f'{name}-{split}-{mask}']=dict(samples_ms=sample,median_ms=statistics.median(sample),indices=ix.tolist(),success_nonempty=r['run2']['nonempty_complete_graphs'],graphs=32,complete_nonempty_graphs_per_second=1000*r['run2']['nonempty_complete_graphs']/sum(sample))
    result=dict(models=meta,panels=reports,timings=timings,complete_by_graph=pairs)
    (args.root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Finished two-Run inference and audits',len(reports),'panels.')

if __name__=='__main__':main()
