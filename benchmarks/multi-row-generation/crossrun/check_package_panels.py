"""Re-run the full panel via the installed Python API and compare to frozen GPU traces."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import time
import statistics

import eggfuse
import mlx.core as mx
import numpy as np

HERE = Path(__file__).resolve().parent
SPLITS = ('iid','left_collision','right_collision')
MASKS = ('none','parents','parents_latent')


def fixtures():
    src = HERE/'data/crossrun_data.py'
    spec = importlib.util.spec_from_file_location('frozen_fixtures',src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {split:mod.dataset(split) for split in SPLITS}


def run(model, mask):
    def infer(a,b,request):
        return eggfuse.infer(model,a,b,request,mask=mask)
    return mx.compile(infer)


def arguments(data,ix):
    return tuple(mx.array(data[k][ix]) for k in ('a','b','requests'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    assert 'site-packages' in Path(eggfuse.__file__).parts
    mx.set_default_device(mx.gpu);panels=fixtures();functions={};model_ids={};records={}
    for arm,seed in itertools.product(('learned','static','aux'),(1703,1709)):
        name=f'{arm}-{seed}';model=eggfuse.load_model(args.root/name,HERE/'compiler/plan.json')
        model_ids[name]=hashlib.sha256((args.root/name/'model.safetensors').read_bytes()).hexdigest()
        for mask in MASKS:functions[name,mask]=run(model,mask)
    reference=json.loads((args.root/'result.json').read_text());checked=bit_exact=0
    for split,data in panels.items():
        for (name,mask),fn in functions.items():
            label=f'{name}-{split}-{mask}'
            with np.load(args.root/'traces'/f'{label}.npz') as z:
                for lo in range(0,len(data['a']),64):
                    ix=slice(lo,lo+64);stages,token=fn(*arguments(data,ix));mx.eval(stages,token)
                    for prefix,stage in zip(('one','two'),stages):
                        for field,values in stage.items():np.testing.assert_array_equal(z[f'{prefix}_{field}'][ix],np.asarray(values))
                    actual=np.ascontiguousarray(np.asarray(token));saved=np.ascontiguousarray(z['token'][ix]);assert actual.dtype==saved.dtype
                    bit_exact+=int((actual.view(np.uint8)==saved.view(np.uint8)).all(axis=(1,2)).sum());checked+=len(actual)
        # Endpoint includes public API, both complete discrete outputs and the whole Pair tensor.
        take=np.random.default_rng(81911).choice(len(data['a']),32,replace=False);lanes=list(functions);samples={lane:[] for lane in lanes}
        for fn in functions.values():
            for i in take[:3]:mx.eval(fn(*arguments(data,slice(i,i+1))))
        kept={lane:[] for lane in lanes}
        for at,i in enumerate(take):
            for lane in lanes[at%len(lanes):]+lanes[:at%len(lanes)]:
                begin=time.perf_counter_ns();out=functions[lane](*arguments(data,slice(i,i+1)));mx.eval(out)
                samples[lane].append((time.perf_counter_ns()-begin)/1e6);kept[lane].append(out)
        for lane in lanes:
            name,mask=lane;label=f'{name}-{split}-{mask}';sample=samples[lane]
            with np.load(args.root/'traces'/f'{label}.npz') as z:
                same_graphs=np.ones(len(take),bool)
                for si,prefix in enumerate(('one','two')):
                    for key in ('active','pointers','fields'):
                        saved=z[prefix+'_'+key][take];observed=np.concatenate([np.asarray(s[si][key]) for s,_ in kept[lane]])
                        same_graphs &= (saved==observed).reshape(len(take),-1).all(-1)
            # Tiny floating differences between single-graph and batched forwards may flip an argmax.
            # Audit the timed outputs on their own, regardless of agreement with the batched run.
            audit_path=HERE/'data/crossrun_audit.py';spec=importlib.util.spec_from_file_location('posthoc',audit_path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            stages=[{k:np.concatenate([np.asarray(s[si][k]) for s,_ in kept[lane]]) for k in ('active','pointers','fields')} for si in (0,1)]
            audited=mod.audit(data['a'][take],data['b'][take],data['requests'][take],*stages)['run2'];wins=audited['nonempty_complete_graphs']
            records[label]=dict(median_ms=statistics.median(sample),samples_ms=sample,nonempty=audited['nonempty_graphs'],complete=wins,graphs_with_identical_discrete_outputs_to_batch64=int(same_graphs.sum()),complete_nonempty_per_second=wins/(sum(sample)/1000))
    assert checked==54*256
    report=dict(installed_module=eggfuse.__file__,models=model_ids,discrete_byte_equal_graphs=checked,pair_token_byte_equal_graphs=bit_exact,graphs_including_interventions=checked,timings=records)
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(checked,bit_exact,flush=True)

if __name__=='__main__':main()
