"""Adaptive research: broaden validation, then freeze for fresh action sequences."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def module(path,name):
    sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def trajectories(model,facts,target,mask,seed,length):
    ids=np.tile(np.flatnonzero(mask),4);z=model.encode(facts[ids]);ok=np.ones(len(ids),bool)
    actions=np.random.default_rng(seed).integers(0,17,(length,len(ids)))
    actions[2]=15;actions[5]=16;actions[8]=actions[7]
    for a in actions:
        z=model.step(z,a);ids=target[ids,a];out=model.decode(z)
        ok &= np.isfinite(z).all(1)&np.isfinite(out).all(1)&((out>=.5)==facts[ids]).all(1)
    return dict(seed=seed,steps=length,trajectories=len(ids),all_steps_exact=int(ok.sum()),rate=float(ok.mean()))


def dependencies(path,seen=None):
    seen={} if seen is None else seen
    key=str(path.relative_to(ROOT))
    if key in seen:return seen
    seen[key]=hashlib.sha256(path.read_bytes()).hexdigest()
    with np.load(path) as weights:
        for name in ('base_path','prior_path'):
            if name in weights:dependencies(Path(str(weights[name])),seen)
    return seen


def main():
    output=ROOT/'out/cell-ridge-readout/verification'
    output.mkdir(parents=True,exist_ok=False)
    teacher=module(ROOT/'benchmarks/cell-real-state/study.py','verification_teacher')
    _,facts,target,train,valid,test=teacher.dataset()
    logs=[];models={}
    # Candidate set fixed before the new validation sequences are evaluated.
    for name,filename in [('gated','gated.py'),('shaped','shaped.py'),('high-order','high_order.py')]:
        impl=module(Path(__file__).parent/filename,'verify_'+name.replace('-','_'))
        path=ROOT/'out/cell-ridge-readout'/name/'model.npz'
        model=impl.load_adapter(path);models[name]=model
        results=[trajectories(model,facts,target,valid,seed,length)
                 for seed,length in ((1049,12),(2027,48),(4093,96))]
        row=dict(name=name,adapter=filename,validation=results,
                 mean_validation=float(np.mean([r['rate'] for r in results])),
                 minimum_validation=min(r['rate'] for r in results))
        logs.append(row);print(row,flush=True)
    winner=max(logs,key=lambda r:(r['mean_validation'],r['minimum_validation']))
    # Write the selection before any of the fresh test sequences are evaluated.
    (output/'selection.json').write_text(json.dumps(dict(selection=winner,validation=logs),indent=2)+'\n')
    model=models[winner['name']]
    fresh=[trajectories(model,facts,target,test,seed,length)
           for seed,length in ((314159,12),(271828,48),(161803,96))]
    weights=ROOT/'out/cell-ridge-readout'/winner['name']/'model.npz'
    result=dict(selection=winner,validation=logs,fresh_test=fresh,
                all_fresh_sequences_at_least_90=all(r['rate']>=.9 for r in fresh),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                weights_dependencies=dependencies(weights),
                disclosure='Adaptive research after earlier test inspection; fresh action sequences only, same held structural states')
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('FINAL',winner['name'],fresh,flush=True)


if __name__=='__main__':main()
