"""Prepare once from real operand exports, then replay only scalar buffers on GPU."""
from model_projection import fold_plan, reference_state
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import run as base
from dataset import canonical


def main():
    import mlx.core as mx
    p=argparse.ArgumentParser()
    for key in ('corpus','slots','model','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    corpus=json.loads(a.corpus.read_text());exports=json.loads(a.slots.read_text());model=dict(np.load(a.model))
    base.POOL_NORMALIZATION=str(model.get('pool_normalization','sum'))
    base.D=int(model['dimension']);base.POOL_OPS=bool(model['pool_ops']);base.OP=model['op'];base.EDGE=model['edge'];base.LITERAL=model['literal']
    cases={r['id']:r for r in exports['cases']};plans={};instances=[];checked=0;slot_reads=0;operands=0;ns=[]
    start=time.perf_counter()
    for r in corpus['records']:
        case=cases[r['id']]
        if case['source_sha256']!=r['source_sha256']:raise ValueError('source mismatch')
        entry,mapping=canonical(case)
        if entry!=r['entry']:raise ValueError('actual runtime input differs from labelled corpus')
        key=base.digest(base.structure(entry))
        if key not in plans:plans[key]=fold_plan(base.Plan(entry),model)
        plan=plans[key];indices={}
        for row in case['rows']:
            node=mapping[row['values'][-1]['eq']]
            fact=[row['table'],[['eq',v['sort'],mapping[v['eq']]] if 'eq' in v else ['literal',v['sort'],v['value']] for v in row['values'][:-1]]]
            fi=entry[node].index(fact)
            for field in row['scalar_fields']:indices[node,fi,field['column']]=field['buffer_index']
        addresses=np.array([indices[pos] for pos in plan.reads],np.int32)
        buffer=np.array(case['scalar_values'],np.float32)
        np.testing.assert_array_equal(buffer[addresses],plan.gather(entry))
        np.testing.assert_allclose(plan.project(buffer[addresses]),reference_state(base.reference(entry),model),atol=1e-4,rtol=1e-4)
        checked+=1;slot_reads+=case['slot_reads'];operands+=case['operand_reads'];ns.append(case['gather_nanoseconds'])
        if r['split']=='test':instances.append((plan,buffer,addresses,r['completion_key']))
    prepare_ms=(time.perf_counter()-start)*1000
    from gpu_model import forward
    fn=forward(model)
    def pack():return np.array([p.project(buf[idx]) for p,buf,idx,_ in instances])
    raw=pack();mx.eval(fn(mx.array(raw)));times=[];packing=[]
    for _ in range(15):
        start=time.perf_counter();batch=pack();packed=time.perf_counter();y=fn(mx.array(batch));mx.eval(y);scores=np.array(y);end=time.perf_counter()
        packing.append((packed-start)*1000);times.append((end-start)*1000)
    labels=list(model['labels']);truth=np.array([labels.index(label) for _,_,_,label in instances]);guess=scores.argmax(1)
    result=dict(scope='Real Graph.argument exports replayed through compiled scalar indices; standalone GPU bench, not live runtime integration',
        cases_verified=checked,operand_reads=operands,actual_slot_reads=slot_reads,layouts=len(plans),
        test=dict(correct=int((truth==guess).sum()),total=len(truth)),
        costs=dict(one_time_adapter_preparation_ms=prepare_ms,test_pack_projection_median_ms=float(np.median(packing)),
            test_pack_gpu_return_median_ms=float(np.median(times)),mean_warm_native_gather_ns_per_case=float(np.mean(ns))),
        storage=dict(layout_matrices_bytes=sum(p.weight.nbytes+p.bias.nbytes+p.metadata.nbytes for p in plans.values()),
            test_state_bytes=raw.nbytes,test_scalar_bytes=sum(b.nbytes for _,b,_,_ in instances),
            test_address_bytes=sum(i.nbytes for _,_,i,_ in instances)),
        input_protocol='existing Cell slot values -> compiled field indices -> affine Cell state; no graph traversal in replay',
        caveats=['one-time canonical adapter still uses full exports, not compiler-native layout discovery',
            'native gather is measured separately; replay timings exclude Rust-Python transport and live lifecycle checks',
            'frozen initial topology; no dynamic unions/deletion in model input',
            'classification only; no authorized mutation or saturation proof'],
        hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','slots','model')})
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
