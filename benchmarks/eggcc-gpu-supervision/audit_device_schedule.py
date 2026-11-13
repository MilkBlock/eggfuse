"""Real control-tree audit with synthetic deterministic Run change policies."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from device_schedule import compile_schedule,initial,current,tick


def reference(control,stages,first_change):
    counts={};events=[];ticks=0
    def execute(node):
        nonlocal ticks
        if isinstance(node,list):
            changed=False
            for child in node:changed=execute(child) or changed
            return changed
        if 'sequence' in node:return execute(node['sequence'])
        if 'run' in node:
            ticks+=1;stage=stages.index(node['run']);n=counts.get(stage,0);counts[stage]=n+1;events.append(stage)
            if len(events)>100000:raise ValueError('audit exceeded reference event budget')
            return first_change and n==0
        if 'repeat' in node:
            ticks+=1;changed=False
            for _ in range(node['repeat']):changed=execute(node['body']) or changed;ticks+=1
            return changed
        changed=False
        while True:
            ticks+=1;again=execute(node['saturate']);ticks+=1;changed=changed or again
            if not again:return changed
    execute(control)
    return events,ticks+1


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);recipe=json.loads(raw)['recipe'];stages=[x['name'] for x in recipe['rulesets']]
    plan,meta=compile_schedule(recipe['control'],stages)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);dp={k:mx.array(v) for k,v in plan.items()};results=[]
    def chunk(state,counts,first_change):
        events=[]
        for _ in range(16):
            stage,_=current(state,dp,mx);safe=mx.maximum(stage,0)
            changed=(stage>=0)&(counts[safe]==0)&first_change
            state,marks=tick(state,dp,mx.array(True),changed,mx)
            counts=counts+((mx.arange(len(stages))==stage)&marks['run_consumed']).astype(mx.int32)
            events.append(stage)
        return state,counts,mx.stack(events)
    kernel=mx.compile(chunk)
    for first in (False,True):
        expected,ticks=reference(recipe['control'],stages,first)
        state=initial(dp,meta['repeat_slots'],mx);counts=mx.zeros(len(stages),mx.int32);events=[]
        for _ in range((ticks+15)//16):
            state,counts,log=kernel(state,counts,mx.array(first));events.append(log)
        log=mx.concatenate(events);_,finished=current(state,dp,mx);mx.eval(log,finished,state)
        actual=[int(x) for x in np.array(log) if x>=0]
        results.append(dict(policy='first_run_per_ruleset_changes' if first else 'no_run_changes',runs=len(actual),reference_runs=len(expected),
                            control_ticks=ticks,run_order_equal=actual==expected,finished=bool(finished),passed=actual==expected and bool(finished)))
    result=dict(scope='Actual Eggcc control tree with synthetic completed-Run change inputs; no graph execution',trace_sha256=hashlib.sha256(raw).hexdigest(),
        instructions=meta['instructions'],saturation_slots=meta['saturation_slots'],repeat_slots=meta['repeat_slots'],rulesets=len(stages),
        static_table_bytes=sum(v.nbytes for v in plan.values()),policies=results,passed=all(x['passed'] for x in results),
        limitations=['Run completion/change signals are synthetic audit policies, not runtime semantic evidence',
                     'Fixed audit budget comes from reference control traversal, not a saturation certificate',
                     'Controller is not yet connected to real Eggcc matching and effects'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
