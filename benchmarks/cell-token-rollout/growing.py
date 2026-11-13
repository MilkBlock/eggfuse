"""Variable-size SubTuple Cell-token fanout and ridge continuation on Metal.
Whole families execute as tensor expressions; no graph reads between stages.
"""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from run import module
from device_stages import complete


def entries(case):
    return [(r['values'][1]['value'],r['values'][2]['value']) for r in case['initial']['rows'] if r['table']=='SubTuple']


def main():
    p=argparse.ArgumentParser();p.add_argument('--training',type=Path,required=True);p.add_argument('--heldout',type=Path,required=True)
    p.add_argument('--reference-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--proposals',type=Path);p.add_argument('--device-stages',action='store_true');a=p.parse_args()
    module('dataset',a.reference_dir/'dataset.py');tr=module('train',a.reference_dir/'train.py')
    train=json.loads(a.training.read_text())['cases'];held=json.loads(a.heldout.read_text())['cases']
    # Distinct observed scalar entrances; no heldout target states or capacities.
    observed=sorted(set(e for c in train for e in entries(c) if e[1]>0))
    roots=np.array(observed,np.float32);root_expanded=[];targets=[];offsets=[]
    for av,bv in observed:
        for j in range(bv):root_expanded.append([av,bv]);offsets.append(j);targets.append([av+j,bv-j])
    x=np.array(root_expanded,np.float32);j=np.array(offsets,np.float32)[:,None];target=np.array(targets,np.float32)
    rng=np.random.default_rng(20319);enc=rng.normal(0,.5,(2,30)).astype(np.float32);eb=rng.normal(0,.2,30).astype(np.float32)
    def encode(v):return np.concatenate([v/16,np.tanh((v/16)@enc+eb)],axis=-1)
    projection=rng.normal(0,.2,(33,128)).astype(np.float32);bias=rng.normal(0,.3,128).astype(np.float32)
    def feature(t,off):
        z=np.concatenate([t,off/16],axis=-1)
        return np.concatenate([z,np.tanh(z@projection+bias)],axis=-1)
    # Fixed regularization, chosen before heldout execution. No test selection.
    w,b=tr.fit(feature(encode(x),j),encode(target),.0001)
    target_readout=np.concatenate([target,target.sum(1)[:,None]],axis=1)
    rw,rb=tr.fit(encode(target),target_readout,.0001)
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    ge,geb,gp,gpb,gw,gb,grw,grb=map(mx.array,[enc,eb,projection,bias,w,b,rw,rb])
    records=[];proposals=[]
    for case in held:
        values=np.array(entries(case),np.float32)
        if len(values)==0:continue
        if not np.all((values[:,1]>=1)&(values[:,1]<=16)&(np.abs(values[:,0])<=32)):
            raise ValueError('outside declared bounded family')
        # Known input lengths control capacity BEFORE any final-state access.
        cap=int(values[:,1].max());n=len(values);offset=mx.arange(cap,dtype=mx.float32)[None,:,None]
        def program(inputs,certified,exact_consumer=False,device=False,suppress=False,ticks=6):
            z=inputs/16;token=mx.concatenate([z,mx.tanh(z@ge+geb)],axis=-1)
            broad=mx.broadcast_to(token[:,None,:],(n,cap,32))
            off=mx.broadcast_to(offset,(n,cap,1));features=mx.concatenate([broad,off/16],axis=-1)
            features=mx.concatenate([features,mx.tanh(features@gp+gpb)],axis=-1)
            predicted=features@gw+gb
            if certified: # compilation-time variant, never data-dependent GPU control
                exact=mx.concatenate([(inputs[:,0,None,None]+off)/16,(inputs[:,1,None,None]-off)/16],axis=-1)
                predicted=mx.concatenate([exact,predicted[:,:,2:]],axis=-1)
            # Stage two directly consumes stage-one token. No graph decode,
            # teacher token, CPU handoff, or per-node dispatch occurs here.
            downstream=predicted@grw+grb
            if exact_consumer: # statically compiled numeric parameter path
                raw=predicted[:,:,:2]*16
                downstream=mx.concatenate([raw,mx.sum(raw,axis=-1,keepdims=True)],axis=-1)
            active=off[:,:,0]<inputs[:,1,None]
            if device:
                return complete(predicted,active,grw,grb,ticks=ticks,suppress=suppress)
            return downstream,active
        # Bind dimensions/constants into each fixed compiled graph before call.
        learned=mx.compile(lambda v:program(v,False));cert=mx.compile(lambda v:program(v,True))
        exact=mx.compile(lambda v:program(v,True,True))
        outputs=[]
        for fn in (learned,cert,exact):
            output,mask=fn(mx.array(values));mx.eval(output,mask)
            outputs.append((np.array(output),np.array(mask)))
        expected=np.zeros((n,cap,3),np.float32)
        for row,(av,bv) in enumerate(values):
            for k in range(cap):expected[row,k]=[av+k,bv-k,av+bv]
        device_metrics=None
        if a.device_stages:
            variants={}
            # Submit the three independent device graphs before inspecting any
            # result. These are exit checks, not yet concurrent CPU supervision.
            pending=[]
            for name,suppress,ticks in [('normal',False,6),('silent_omission',True,6),('budget_exhaustion',False,1)]:
                fn=mx.compile(lambda v,s=suppress,t=ticks:program(v,False,device=True,suppress=s,ticks=t))
                ticket=fn(mx.array(values));mx.async_eval(ticket)
                pending.append((name,ticket))
            for name,ticket in pending:
                started=time.perf_counter()
                actual,mask,stage,trace,exhausted=map(np.array,ticket)
                wait_and_copy=time.perf_counter()-started
                started=time.perf_counter()
                expected_mask=np.arange(cap)[None,:]<values[:,1,None]
                missing=int((expected_mask&~mask).sum())
                unexpected=int((mask&~expected_mask).sum())
                wrong=int((np.any(np.rint(actual)!=expected,axis=-1)&mask).sum())
                variants[name]=dict(stage=int(stage),budget_exhausted=bool(exhausted),
                    missing_tokens=missing,unexpected_tokens=unexpected,wrong_tokens=wrong,
                    cpu_confirmed=not(missing or unexpected or wrong or bool(exhausted)),
                    cpu_check_seconds=time.perf_counter()-started,
                    wait_and_copy_seconds=wait_and_copy,device_trace=trace.tolist())
                if name=='normal':
                    np.testing.assert_allclose(actual[mask],outputs[0][0][mask],rtol=1e-4,atol=1e-4)
                    assert np.array_equal(mask,outputs[0][1]) and int(stage)==2 and not exhausted
                elif name=='silent_omission':
                    assert missing==n and int(stage)==2 and not variants[name]['cpu_confirmed']
                else:
                    assert exhausted and not variants[name]['cpu_confirmed']
            device_metrics=variants
        # Actual final graph is read only AFTER both GPU variants finish.
        final_keys={(r['values'][1]['value'],r['values'][2]['value']) for r in case['final']['rows'] if r['table']=='SubTuple'}
        valid=outputs[0][1];assert np.array_equal(valid,outputs[1][1])
        assert int(valid.sum())==int(values[:,1].sum())
        assert all(tuple(map(int,e[:2])) in final_keys for e in expected[valid])
        np.testing.assert_array_equal(outputs[2][0][valid],expected[valid])
        # Independent NumPy evaluation of the learned, uncorrected path.
        base=encode(values);broad=np.broadcast_to(base[:,None,:],(n,cap,32))
        off=np.broadcast_to(np.arange(cap,dtype=np.float32)[None,:,None],(n,cap,1))
        reference=(feature(broad,off)@w+b)@rw+rb
        np.testing.assert_allclose(outputs[0][0],reference,rtol=1e-4,atol=1e-4)
        novel=np.broadcast_to(np.array([tuple(v) not in set(observed) for v in values])[:,None],valid.shape)&valid
        proposals.append(dict(id=case['id'],values=outputs[0][0][valid].tolist()))
        metrics=[]
        for output,mask in outputs:
            rounded=np.rint(output[mask]);truth=expected[mask]
            metrics.append(dict(exact_rounded_tokens=int(np.all(rounded==truth,axis=1).sum()),
                tokens=len(truth),rejected_output_tokens=int(np.any(rounded!=truth,axis=1).sum()),
                unseen_entrance_tokens=int(novel.sum()),unseen_entrance_correct=int(np.all(np.rint(output[novel])==expected[novel],axis=1).sum()),
                max_abs_error=float(np.abs(output[mask]-truth).max())))
        records.append(dict(id=case['id'],device_stages=device_metrics,entrance_cells=n,token_width=32,allocated_output_tokens=n*cap,
            active_output_tokens=int(valid.sum()),padding_tokens=int((~valid).sum()),
            token_buffer_bytes=n*cap*32*4,learned=metrics[0],certified_parameter_channels=metrics[1],compiled_parameter_continuation=metrics[2]))
    result=dict(scope='Standalone fixed GPU fanout and token continuation for bounded SubTuple Cells; not full saturation or runtime takeover',
        provenance={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [a.training,a.heldout,a.reference_dir/'train.py']},
        training_distinct_entrances=len(observed),training_tokens=len(target),training_length_range=[min(b for _,b in observed),max(b for _,b in observed)],
        training_start_range=[min(av for av,_ in observed),max(av for av,_ in observed)],
        token_width=32,backpropagation=False,intermediate_host_reads=0,intermediate_graph_decodes=0,
        capacity_source='initial SubTuple lengths only, admitted length 1..16; no future state',
        heldout=records,engine_operations_removed=0,
        limitations=['overlapping entrance outputs are not deduplicated on GPU','CPU checks the exact affine arithmetic at exit; rounded ridge output is not a proof',
        'family expands suffix Cells only; cross-entry joins and other rules remain uncovered','hidden channels are learned, not proven sufficient state',
        'parameter channel exactness does not make downstream ridge exact','no throughput claim; no CPU residual runtime integration'])
    if a.proposals:
        a.proposals.parent.mkdir(parents=True,exist_ok=True)
        a.proposals.write_text(json.dumps(dict(schema='learned-tuple-token-proposals/v1',runtime_sha256=hashlib.sha256(a.heldout.read_bytes()).hexdigest(),cases=proposals),indent=2)+'\n')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
