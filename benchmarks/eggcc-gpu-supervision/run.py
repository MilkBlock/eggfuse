"""Real eggcc binding replay with exhaustive CPU numeric supervision.
No GPU effects are applied to the live graph in this first diagnostic version.
"""
import argparse,collections,hashlib,importlib.util,json,subprocess,tempfile,time
from pathlib import Path
import numpy as np
import mlx.core as mx


def supervise(proposed,reference,marked):
    start=time.perf_counter_ns()
    bad=~np.isfinite(proposed)|(proposed!=reference)
    rows=bad.any(1);silent=rows&~marked
    checking=(time.perf_counter_ns()-start)/1e9
    start=time.perf_counter_ns();corrected=proposed.copy();corrected[bad]=reference[bad]
    repair=(time.perf_counter_ns()-start)/1e9
    assert np.array_equal(corrected,reference)
    return rows,silent,bad,checking,repair


def main():
    p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True)
    p.add_argument('--oracle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('affine',a.compiler);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    raw=json.loads(a.trace.read_text());assert raw['strict_audit_reference_equal'];rules=raw['recipe']['rules']
    counts=collections.Counter();marks=[];groups=collections.defaultdict(list);plans={};compile_fail={}
    for rid,r in enumerate(rules):
        if not any(o.get('kind')=='compute' for o in r['effects']):continue
        inputs=[i for i,s in enumerate(r['slots']) if s['definition']=='query' and s['sort']['kind']=='i64']
        try:plans[rid]=c.Affine(r,inputs,[1<<20]*len(inputs))
        except c.Unsupported as e:compile_fail[rid]=str(e)
    start=time.perf_counter()
    for run in raw['runs']:
        for index,b in enumerate(run['audit']['bindings']):
            counts['all_bindings']+=1;rid=b['rule']
            if rid not in plans and rid not in compile_fail:
                counts['cpu_only_non_scalar']+=1
                marks.append(dict(run=run['ordinal'],binding=index,rule=rid,kind='cpu_only',reason='outside compiled numeric region'))
                continue
            counts['scalar_bindings']+=1;location=dict(run=run['ordinal'],binding=index,rule=rid)
            if rid in compile_fail:
                marks.append(dict(**location,kind='cpu_only',reason=compile_fail[rid]));counts['cpu_only']+=1;continue
            env={v['slot']:v['value'] for v in b['values']};plan=plans[rid]
            values=[env[s].get('value') for s in plan.inputs]
            if not plan.eligible(values):
                marks.append(dict(**location,kind='preflight_mark',reason='input outside exact f32 domain'));counts['preflight_marked']+=1;continue
            groups[rid].append((location,values))
    packing=time.perf_counter()-start
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    cpu_reference=cpu_check=cpu_repair=gpu_seconds=oracle_process=0.;metrics=[];fault=[]
    with tempfile.TemporaryDirectory() as d:
        for rid,records in groups.items():
            plan=plans[rid];cases=[v for _,v in records]
            req=Path(d)/'request.json';out=Path(d)/'out.json'
            req.write_text(json.dumps(dict(rule=rules[rid],inputs=plan.inputs,cases=cases)))
            start=time.perf_counter();subprocess.run([str(a.oracle.resolve()),str(req),str(out)],check=True,timeout=1.)
            oracle_process+=time.perf_counter()-start;native=json.loads(out.read_text());cpu_reference+=native['cpu_reference_seconds']
            assert all(row is not None for row in native['rows'])
            expected=np.array([[row[str(slot)] for slot in plan.destinations] for row in native['rows']],np.float32)
            w,b=mx.array(plan.coefficients),mx.array(plan.bias)
            def kernel(x):
                y=x@w+b
                return y,~mx.all(mx.isfinite(y),axis=1)
            fn=mx.compile(kernel)
            start=time.perf_counter();got,device_marks=fn(mx.array(np.array(cases,np.float32)));mx.eval(got,device_marks);got=np.array(got);device_marks=np.array(device_marks)
            request_seconds=time.perf_counter()-start;gpu_seconds+=request_seconds
            rows,silent,bad,check,repair=supervise(got,expected,device_marks)
            cpu_check+=check;cpu_repair+=repair;counts['gpu_checked']+=len(got);counts['gpu_marked']+=int(device_marks.sum());counts['cpu_detected']+=int(rows.sum());counts['silent_errors']+=int(silent.sum())
            for index in np.flatnonzero(device_marks):
                marks.append(dict(**records[index][0],kind='gpu_mark',reason='device nonfinite result'))
            for index in np.flatnonzero(rows):
                marks.append(dict(**records[index][0],kind='cpu_detected',reason='numeric mismatch',slots=[plan.destinations[k] for k in np.flatnonzero(bad[index])]))
            # Known injected truth, kept separate from natural failures. Include
            # a proactive mark, a silent wrong value and a silent nonfinite value.
            injected=got.copy();injected[0,0]+=1
            rr,ss,bb,_,_=supervise(injected,expected,np.zeros(len(got),bool));assert rr[0] and ss[0]
            explicit=np.zeros(len(got),bool);explicit[0]=True
            rr,ss,bb,_,_=supervise(injected,expected,explicit);assert rr[0] and not ss[0]
            injected[0,0]=np.nan;rr,ss,bb,_,_=supervise(injected,expected,np.zeros(len(got),bool));assert rr[0] and ss[0]
            fault.append(dict(rule=rid,marked_wrong_detected=True,silent_wrong_detected=True,silent_nan_detected=True))
            metrics.append(dict(rule=rid,bindings=len(records),unique_output_columns=len(plan.destinations),cpu_reference_seconds=native['cpu_reference_seconds'],cpu_comparison_seconds=check,cpu_repair_copy_seconds=repair,gpu_first_request_seconds=request_seconds))
    checked=counts['gpu_checked'];issues=counts['gpu_marked']+counts['silent_errors'];supervision=cpu_reference+cpu_check
    mark_path=a.output.with_suffix('.marks.json')
    mark_path.parent.mkdir(parents=True,exist_ok=True)
    mark_path.write_text(json.dumps(marks,indent=2)+'\n')
    result=dict(scope='Real sum-bits eggcc Pass 3 binding replay; numerical GPU supervision, no live GPU takeover',
        program_sha256=raw['program_sha256'],strict_audit_reference_equal=raw['strict_audit_reference_equal'],
        hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [a.trace,a.compiler,a.oracle]},counts=dict(counts),
        rates=dict(gpu_coverage_of_all_bindings=checked/counts['all_bindings'],gpu_coverage_of_scalar_bindings=checked/counts['scalar_bindings'],
            cpu_only_of_scalar_bindings=counts['cpu_only']/counts['scalar_bindings'],
            preflight_marked_of_scalar_bindings=counts['preflight_marked']/counts['scalar_bindings'],
            gpu_marked_of_checked=counts['gpu_marked']/checked if checked else None,
            cpu_detected_of_checked=counts['cpu_detected']/checked if checked else None,
            silent_errors_of_checked=counts['silent_errors']/checked if checked else None,
            cpu_only_discovered_share_of_reported_issues=counts['silent_errors']/issues if issues else None),
        cpu_metrics=dict(reference_seconds=cpu_reference,comparison_seconds=cpu_check,repair_copy_seconds=cpu_repair,
            checks_per_second=checked/supervision if supervision else None,microseconds_per_checked_binding=supervision*1e6/checked if checked else None,
            oracle_process_seconds=oracle_process,entry_routing_seconds=packing),gpu_first_requests_seconds=gpu_seconds,
        groups=metrics,local_marks_path=str(mark_path),local_mark_counts=dict(collections.Counter(m['reason'] for m in marks)),fault_injection=fault,
        injected_fault_metrics=dict(known_errors=3*len(fault),detected_errors=3*len(fault),proactively_marked_errors=len(fault),cpu_only_discovered_errors=2*len(fault),detection_rate=1. if fault else None),
        fault_scope='Three host-side output/flag fault controls per GPU rule batch, never included in natural rates',
        denominator_notes=['Uncovered scalar bindings are cpu_only, not model errors','Issue share is null when no issues, not zero-percent recall',
        'CPU oracle recomputes every GPU-covered scalar result; no sampled verification','Reference and comparison timings exclude JSON/process startup, reported separately',
        'Reference executable is debug build; these are diagnostic rates, not optimized CPU limits'],
        runtime_note='CPU-only and domain-marked bindings already execute on the exact original CPU run; covered corrections affect replay outputs only',
        natural_correction_graph_mutations=0)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('local_marks','groups','fault_injection')},indent=2))
if __name__=='__main__':main()
