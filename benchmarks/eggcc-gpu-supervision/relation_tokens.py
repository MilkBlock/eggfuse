"""Actual Run Eq-partition audit and renaming-invariant floating encoding.

The encoder consumes exact locally normalized partitions, not global IDs. It
is a representation diagnostic, not a trained completion predictor. Ambiguous
local inputs expose missing boundary context before attempting ridge training.
"""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import time

import mlx.core as mx
import numpy as np


def partition(ports, phase, rename=lambda x:x):
    seen = {}
    return tuple(seen.setdefault((p['sort'],rename(p[phase])), i) for i,p in enumerate(ports))


def audit(trace):
    if not trace.get('relations'):
        raise ValueError('requires actual pre/post Run root observation')
    states = defaultdict(list)
    same_run = defaultdict(list)
    by_width = defaultdict(list)
    contextual = defaultdict(list)
    contextual_same_run = defaultdict(list)
    incidence_entries = 0
    rows = []
    started = time.perf_counter()
    for run in trace['runs']:
        incidence = defaultdict(Counter)
        for binding in run['audit']['bindings']:
            for port in binding['eq_ports']:
                incidence[(port['sort'],port['before'])][binding['rule'],port['slot']] += 1
                incidence_entries += 1
        for index,binding in enumerate(run['audit']['bindings']):
            ports = binding['eq_ports']
            before,after = partition(ports,'before'),partition(ports,'after')
            # Huge, unrelated identity magnitudes must not alter local states.
            assert before == partition(ports,'before',lambda x:(1<<100)+17*x)
            assert after == partition(ports,'after',lambda x:(1<<100)+17*x)
            # Existing equality may merge, but cannot split under this trace.
            for i in range(len(ports)):
                for j in range(i):
                    if before[i]==before[j]:assert after[i]==after[j]
            scalar = tuple((v['slot'],json.dumps(v['value'],sort_keys=True))
                           for v in binding['values'] if 'eq' not in v['value'])
            key = (binding['rule'],before,scalar)
            record = dict(run=run['ordinal'],binding=index,rule=binding['rule'],before=before,after=after,
                root_changed=any(p['before']!=p['after'] for p in ports))
            context = tuple(tuple(sorted(incidence[p['sort'],p['before']].items())) for p in ports)
            contextual[(key,context)].append(record)
            contextual_same_run[(run['ordinal'],key,context)].append(record)
            states[key].append(record)
            same_run[(run['ordinal'],key)].append(record)
            rows.append(record)
            if ports:
                by_width[len(ports)].extend([before,after])
    normalization_seconds = time.perf_counter()-started
    conflicts=[]
    for records in same_run.values():
        outcomes={r['after'] for r in records}
        if len(outcomes)>1:
            examples=[];seen=set()
            for r in records:
                if r['after'] not in seen:examples.append(r);seen.add(r['after'])
            conflicts.append(dict(instances=len(records),outcomes=len(outcomes),examples=examples))
    # An empirical ceiling for deterministic prediction from this exact local
    # signature. This is dataset ambiguity, not a statistical test estimate.
    unavoidable=sum(len(rs)-max(Counter(r['after'] for r in rs).values()) for rs in states.values())
    context_report=dict(
        description='Pre-Run shared-root incidence counts by neighboring rule and input slot; no post-Run information',
        registered_eq_port_occurrences=incidence_entries,
        same_run_ambiguous_groups=sum(len({r['after'] for r in rs})>1 for rs in contextual_same_run.values()),
        deterministic_minimum_errors=sum(len(rs)-max(Counter(r['after'] for r in rs).values()) for rs in contextual.values()),
        cost='CPU builds a per-Run incidence index for this diagnostic; not free static Bake wiring')
    return rows,by_width,conflicts,normalization_seconds,unavoidable,context_report


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    trace=json.loads(a.trace.read_text());rows,groups,conflicts,cpu_seconds,unavoidable,context_report=audit(trace)
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    rng=np.random.default_rng(4317);kernels=[]
    for width,partitions in sorted(groups.items()):
        indices=np.array(partitions,np.int32)
        code=rng.normal(0,.4,(width,8)).astype(np.float32)
        projection=rng.normal(0,1/(width*8)**.5,(width*8,32)).astype(np.float32)
        gc,gp=mx.array(code),mx.array(projection)
        def build(c,w,n):
            return mx.compile(lambda i:mx.tanh(c[i].reshape(i.shape[0],n*8)@w))
        fn=build(gc,gp,width);start=time.perf_counter();output=fn(mx.array(indices));mx.eval(output)
        output=np.array(output);seconds=time.perf_counter()-start
        reference=np.tanh(code[indices].reshape(len(indices),width*8)@projection)
        np.testing.assert_allclose(output,reference,rtol=1e-4,atol=1e-5)
        # Same local relation gives exactly the same encoded state. This says
        # nothing about whether the state contains sufficient future context.
        signatures={}
        for part,token in zip(partitions,output):
            if part in signatures:np.testing.assert_array_equal(token,signatures[part])
            else:signatures[part]=token
        kernels.append(dict(eq_ports=width,rows=len(indices),distinct_partitions=len(signatures),
            device_request_seconds=seconds,latent_width=32))
    report=dict(scope='Full-program Eq relation observation and floating encoding diagnostic; no GPU graph takeover',
        trace_sha256=hashlib.sha256(a.trace.read_bytes()).hexdigest(),program_sha256=trace['program_sha256'],
        bindings=len(rows),observed_root_changes=sum(r['root_changed'] for r in rows),
        local_partition_changes=sum(r['before']!=r['after'] for r in rows),
        unchanged_partition_baseline_accuracy=sum(r['before']==r['after'] for r in rows)/len(rows),
        same_run_ambiguous_groups=len(conflicts),same_run_conflicts=conflicts,
        boundary_context=context_report,
        deterministic_local_signature_minimum_errors=unavoidable,
        local_signature_empirical_max_accuracy=1-unavoidable/len(rows),
        cpu_normalization_and_audit_seconds=cpu_seconds,renaming_invariance=True,
        kernels=kernels,backpropagation=False,trained_model=False,gpu_completed_bindings=0,
        limitations=['Only relationships among matched input ports are observed, not new RHS result ports',
        'Run-end changes include other bindings, congruence and boundary effects, not just this Cell',
        'Local normalization still reads exact CPU roots and has not been moved into static GPU wiring',
        'The floating encoder has fixed random weights and is not a completion prediction model',
        'Conflicting local inputs require boundary context or CPU correction; IDs alone do not supply that context'])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('kernels','same_run_conflicts')},indent=2))


if __name__=='__main__':main()
