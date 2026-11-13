"""Check saved pre-effect input encodings; not autonomous runtime execution."""
import argparse,hashlib,json,time
from collections import defaultdict
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from multi_entry_ridge import input_rows,template,neighborhood_template,encode,scalar
from device_input_features import compile_inputs,encode_inputs


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw)
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture audit missing')
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);groups=defaultdict(list)
    for run in trace['runs']:
        for b in run['audit']['bindings']:groups[b['rule']].append(b)
    cases=batches=numeric=fallback=blocked=outside=0;maxdiff=0.;seconds=0.;finite=True
    kernel=mx.compile(lambda i,l:encode_inputs(i,l,mx))
    for rid,bindings in groups.items():
        rule=trace['recipe']['rules'][rid];layout=compile_inputs(rule);roles,q=template(rule);nr,nq=neighborhood_template(rule)
        dl={k:mx.array(v) for k,v in layout.items()};s=len(rule['slots'])
        for start in range(0,len(bindings),64):
            batch=bindings[start:start+64];n=len(batch);cases+=n;batches+=1
            inp=dict(roots=np.zeros((n,s),np.int32),valid=np.zeros((n,s),bool),numeric=np.zeros((n,s),bool),numbers=np.zeros((n,s),np.float32),
                scalar_codes=np.zeros((n,s,64),np.float32),scalar_valid=np.zeros((n,s),bool))
            expected_seed=[];expected_q=[]
            for i,b in enumerate(batch):
                rows=input_rows(b);classes={}
                for slot,value,key in rows:
                    inp['valid'][i,slot]=True
                    if key is not None:inp['roots'][i,slot]=classes.setdefault(key,len(classes));continue
                    v=value.get('value')
                    supported=isinstance(v,(float,int)) and not isinstance(v,bool) and np.isfinite(v) and abs(v)<=np.finfo(np.float32).max and float(np.float32(v))==v
                    if supported:inp['numeric'][i,slot]=True;inp['numbers'][i,slot]=v;numeric+=1
                    else:inp['scalar_codes'][i,slot]=scalar(value);inp['scalar_valid'][i,slot]=True;fallback+=1
                expected_seed.append(encode(rows,roles,'class-balanced'))
                expected_q.append(np.concatenate([q,encode(rows,nr,'class-balanced'),nq]))
            di={k:mx.array(v) for k,v in inp.items()};mx.eval(di,dl)
            begin=time.monotonic();out,marks=kernel(di,dl);mx.eval(out,marks);seconds+=time.monotonic()-begin
            blocked+=int((~np.array(out['input_ready'])).sum())
            for key,expected in [('seed',expected_seed),('q',expected_q)]:
                actual=np.array(out[key]);finite=finite and bool(np.isfinite(actual).all());delta=np.abs(actual-np.array(expected))
                maxdiff=max(maxdiff,float(delta.max(initial=0)));outside+=int((delta>2e-5).sum())
    result=dict(scope='Saved successful query inputs, GPU seed/neighborhood/scalar encoding audit, not runtime matching',trace_sha256=hashlib.sha256(raw).hexdigest(),
        cases=cases,templates=len(groups),batches=batches,gpu_numeric_scalar_occurrences=numeric,resident_fallback_scalar_occurrences=fallback,
        blocked=blocked,max_absolute_difference=maxdiff,outside_tolerance=outside,finite=finite,gpu_seconds_including_compilation=seconds,
        passed=finite and blocked==0 and outside==0,backpropagation=False,accuracy_gain_claimed=False,
        limitations=['CPU supplies saved query slots and exact typed equality classes for this audit',
                     'Non-f32-exact numeric values and categorical scalars use CPU prepared resident codes',
                     'Cold timings exclude packing, upload/readback and matching; no end-to-end speed claim'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
