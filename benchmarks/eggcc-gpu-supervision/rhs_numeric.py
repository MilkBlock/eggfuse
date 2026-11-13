"""Execute input-ready scalar nodes of whole-program RHS plans on Metal.

Actual successful CPU bindings provide the inputs. This is replay, not GPU
query completion. Exact identity/result ports stay outside floating arithmetic.
"""
import argparse
from collections import defaultdict, Counter
import json
from pathlib import Path
import time

import mlx.core as mx
import numpy as np

from rhs_tokens import compile_rule


SUPPORTED = {'+', '-', '*', '/', 'max', 'min', 'bool-<', 'and', 'or'}


def ready(plan):
    available = {i for i,s in enumerate(plan['sources'])
                 if ('input_slot' in s or 'literal' in s) and s['sort']['kind'] in ('i64', 'bool')}
    ops = []
    for op in plan['operations']:
        if op['kind']=='compute' and op['call']['primitive'] in SUPPORTED and all(a in available for a in op['args']):
            ops.append(op)
            available.add(op['result'])
    return ops


def build(plan, ops):
    needed = {a for op in ops for a in op['args']}
    inputs = [i for i in sorted(needed) if 'input_slot' in plan['sources'][i]]
    literals = {i:s['literal'] for i,s in enumerate(plan['sources']) if i in needed and 'literal' in s}

    def execute(x):
        values = {s:x[:,i] for i,s in enumerate(inputs)}
        values.update({s:mx.full((x.shape[0],),v,dtype=mx.float32) for s,v in literals.items()})
        valid = {s:mx.isfinite(v) & (mx.abs(v)<=2**20) for s,v in values.items()}
        outputs, masks = [], []
        for op in ops:
            a,b = [values[s] for s in op['args']]
            ok = valid[op['args'][0]] & valid[op['args'][1]]
            name = op['call']['primitive']
            if name=='+': v=a+b
            elif name=='-': v=a-b
            elif name=='*': v=a*b
            elif name=='/':
                ok = ok & (b!=0)
                q=a/mx.where(b!=0,b,1)
                v=mx.where(q<0,mx.ceil(q),mx.floor(q))
            elif name=='max': v=mx.maximum(a,b)
            elif name=='min': v=mx.minimum(a,b)
            elif name=='bool-<': v=(a<b).astype(mx.float32)
            elif name=='and': v=((a!=0)&(b!=0)).astype(mx.float32)
            elif name=='or': v=((a!=0)|(b!=0)).astype(mx.float32)
            else: raise ValueError(name)
            ok = ok & mx.isfinite(v) & (mx.abs(v)<=2**24)
            values[op['result']],valid[op['result']]=v,ok
            outputs.append(v); masks.append(ok)
        return mx.stack(outputs,axis=1),mx.stack(masks,axis=1)

    return inputs, mx.compile(execute)


def reference(plan, ops, binding):
    inputs={x['slot']:x['value'] for x in binding['values']}
    env={i:inputs[s['input_slot']]['value'] for i,s in enumerate(plan['sources'])
         if 'input_slot' in s and s['sort']['kind'] in ('i64','bool')}
    env.update({i:s['literal'] for i,s in enumerate(plan['sources']) if 'literal' in s})
    out=[]
    for op in ops:
        a,b=[env[s] for s in op['args']]; name=op['call']['primitive']
        if a is None or b is None: v=None
        elif name=='+': v=a+b
        elif name=='-': v=a-b
        elif name=='*': v=a*b
        elif name=='/': v=None if b==0 else (abs(a)//abs(b))*(-1 if (a<0)!=(b<0) else 1)
        elif name=='max': v=max(a,b)
        elif name=='min': v=min(a,b)
        elif name=='bool-<': v=a<b
        elif name=='and': v=bool(a and b)
        elif name=='or': v=bool(a or b)
        else: raise ValueError(name)
        env[op['result']]=v;out.append(v)
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    t=json.loads(a.trace.read_text());plans=[compile_rule(r) for r in t['recipe']['rules']]
    assert t['all_slots'] and mx.metal.is_available();mx.set_default_device(mx.gpu)
    rows=defaultdict(list)
    for run in t['runs']:
        for b in run['audit']['bindings']:rows[b['rule']].append((run['ordinal'],b))
    report=[];marks=[];counts=Counter()
    for rid,plan in enumerate(plans):
        ops=ready(plan)
        if not ops or not rows[rid]:continue
        inputs,kernel=build(plan,ops);batch=[];bindings=rows[rid]
        for ordinal,binding in bindings:
            env={v['slot']:v['value'] for v in binding['values']}
            batch.append([env[plan['sources'][s]['input_slot']]['value'] for s in inputs])
        # Reject domains before f32 conversion: a huge integer must not round
        # into the accepted interval. This preparation cost is not GPU work.
        admitted=np.array([all(isinstance(v,(int,bool)) and abs(v)<=2**20 for v in row) for row in batch])
        x=np.array([[v if abs(v)<=2**20 else 0 for v in row] for row in batch],dtype=np.float32).reshape(len(batch),len(inputs))
        start=time.perf_counter();values,mask=kernel(mx.array(x));mx.eval(values,mask)
        values,mask=np.array(values),np.array(mask);device_seconds=time.perf_counter()-start
        mask &= admitted[:,None]
        start=time.perf_counter();checked=accepted=0
        for row,(ordinal,binding) in enumerate(bindings):
            expected=reference(plan,ops,binding)
            for col,(op,truth) in enumerate(zip(ops,expected)):
                checked+=1
                if not mask[row,col]:reason='domain or primitive failure'
                elif truth is None or values[row,col]!=truth:reason='CPU detected numeric mismatch'
                else:
                    accepted+=1;counts[op['call']['primitive']]+=1;continue
                marks.append(dict(run=ordinal,rule=rid,operation=op['operation'],reason=reason))
        report.append(dict(rule=rid,bindings=len(bindings),checked_scalar_operations=checked,
            accepted_scalar_operations=accepted,cpu_check_seconds=time.perf_counter()-start,
            device_request_seconds=device_seconds))
    result=dict(scope='Full-recipe scalar dataflow replay on Metal; CPU supplies matches and commits all graph effects',
        rules=len(plans),rules_with_executed_numeric_kernels=len(report),
        checked_scalar_operations=sum(r['checked_scalar_operations'] for r in report),
        accepted_scalar_operations=sum(r['accepted_scalar_operations'] for r in report),
        accepted_primitives=dict(counts),marks=marks,rules_report=report,
        gpu_completed_bindings=0,backpropagation=False,
        limitations=['No GPU query, constructor, union or mutable update takeover',
        'Batches combine saved Runs for replay only, never authorize reordering effects',
        'CPU reference is independent bounded arithmetic, not the native primitive oracle',
        'Division is approximate f32 with exact CPU comparison; mismatches require correction',
        'Request times include compile/copy; no end-to-end speedup claim'])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rules_report','marks')},indent=2))


if __name__=='__main__':main()
