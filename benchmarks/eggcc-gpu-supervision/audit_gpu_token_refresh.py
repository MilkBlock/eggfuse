"""Check device encoding against the ridge representation on saved complete states.

CPU-captured post-states are oracle inputs for this encoding audit, not runtime
inputs or predictions. No training, fitting, model selection or speedup claim.
"""
import argparse
from collections import defaultdict
import hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from multi_entry_ridge import template,output_rows,encode,scalar
from device_token_refresh import encode_batch


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw)
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):
        raise ValueError('capture audit missing')
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    groups=defaultdict(list);excluded=0
    for run in trace['runs']:
        for binding in run['audit']['bindings']:
            if not binding['rhs']['completed'] or any('unavailable' in v for v in binding['rhs']['slots']):excluded+=1;continue
            groups[binding['rule']].append(binding)
    preparation=reference_seconds=upload=execution=download=0.;cases=batches=outside=0;maximum=0.;finite=True;max_slots=0;peak_mask=0;input_bytes=0
    kernel=mx.compile(lambda *xs:encode_batch(*xs,mx))
    for rid,bindings in groups.items():
        start=time.monotonic();rule=trace['recipe']['rules'][rid];roles,_=template(rule);width=len(rule['slots'])
        names={s['sort']['name'] for s in rule['slots'] if s['sort']['kind']=='eq'};sort_codes={s:i for i,s in enumerate(sorted(names))}
        sorts=np.array([[sort_codes.get(s['sort']['name'],-1) for s in rule['slots']]],np.int32)
        is_eq=np.array([[s['sort']['kind']=='eq' for s in rule['slots']]],bool)
        preparation+=time.monotonic()-start
        max_slots=max(max_slots,width)
        for begin in range(0,len(bindings),64):
            batch=bindings[begin:begin+64];n=len(batch);batches+=1;cases+=n
            start=time.monotonic();roots=np.zeros((n,width),np.int32);valid=np.zeros((n,width),bool);codes=np.zeros((n,width,64),np.float32)
            for i,b in enumerate(batch):
                # Encoding depends on typed equality, not global identity magnitude.
                classes={}
                for slot,value,key in output_rows(b):
                    valid[i,slot]=True
                    if key is not None:
                        roots[i,slot]=classes.setdefault(key,len(classes))
                    else:codes[i,slot]=scalar(value)
            arrays=(roots,sorts,is_eq,valid,roles[None,:,:],codes)
            input_bytes+=sum(x.nbytes for x in arrays);peak_mask=max(peak_mask,n*width*width)
            preparation+=time.monotonic()-start
            start=time.monotonic();expected=np.array([encode(output_rows(b),roles,'class-balanced') for b in batch]);reference_seconds+=time.monotonic()-start
            start=time.monotonic();device=[mx.array(x) for x in arrays];mx.eval(device);upload+=time.monotonic()-start
            start=time.monotonic();out=kernel(*device);mx.eval(out);execution+=time.monotonic()-start
            start=time.monotonic();actual=np.array(out);download+=time.monotonic()-start
            finite=finite and bool(np.isfinite(actual).all());delta=np.abs(actual-expected)
            maximum=max(maximum,float(delta.max(initial=0)));outside+=int((delta>2e-5).sum())
    result=dict(trace_sha256=hashlib.sha256(raw).hexdigest(),scope='Oracle captured-state encoding audit, not predicted completion or autonomous GPU runtime',
        cases=cases,excluded_incomplete=excluded,template_groups=len(groups),batches=batches,max_slots=max_slots,
        maximum_partition_mask_elements=peak_mask,total_uploaded_input_bytes=input_bytes,
        preparation_seconds=preparation,cpu_reference_encoding_seconds=reference_seconds,gpu_upload_seconds=upload,
        gpu_encoding_seconds_including_compilation=execution,readback_seconds=download,
        max_absolute_difference=maximum,outside_tolerance=outside,absolute_tolerance=2e-5,finite=finite,passed=finite and outside==0,
        backpropagation=False,accuracy_gain_claimed=False,
        limitations=['Audit remaps exact typed identities to local class labels; not a runtime identity allocator',
                     'Dynamic scalar codes prepared on CPU for audit; runtime scalar production remains required',
                     'Template groups and batches selected on CPU in this audit driver',
                     'Dense Eq-partition masks have quadratic slot cost',
                     'Cold aggregate costs include multiple compiled shapes; not a runtime speed benchmark'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
