"""Real source-only continuation probe; no CPU consumer match list supplied."""
import argparse,hashlib,json
from collections import defaultdict
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from cell_token_successors import compile_catalog
from lower_device_entries import lower,tensors
from multi_entry_ridge import output_rows,template,encode,scalar
from device_entry_transition import compile_features,step


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw);recipe=trace['recipe']
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture audit missing')
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);saved=np.load(a.model)
    if str(saved['encoding'])!='class-history-neighborhood-input' or int(saved['channels'])!=4:raise ValueError('model interface mismatch')
    model={k:mx.array(saved[k]) for k in ('w','coef')};sources={}
    for run in trace['runs']:
        for b in run['audit']['bindings']:
            if b['rhs']['completed'] and all('unavailable' not in s for s in b['rhs']['slots']):sources.setdefault(b['rule'],b)
    lowered=lower(recipe,compile_catalog(recipe),source_slots=True);records=[]
    dev=lambda d:{k:mx.array(v) for k,v in d.items()}
    for entry in lowered['entries']:
        rid=entry['producer']
        if rid not in sources:continue
        b=sources[rid];rows=output_rows(b);width=lowered['slot_width'];kw=lowered['key_width']
        s=dict(keys=np.full((2,kw),-1,np.int32),tokens=np.zeros((2,128),np.float32),slots=np.full((2,width),-1,np.int32),slot_roots=np.full((2,width),-1,np.int32),
            slot_valid=np.zeros((2,width),bool),generation=np.array([1,0],np.int32),scalar_numbers=np.zeros((2,width),np.float32),scalar_numeric=np.zeros((2,width),bool),
            scalar_codes=np.zeros((2,width,64),np.float32),scalar_valid=np.zeros((2,width),bool))
        for k in ('present','visible','active','settled'):s[k]=np.array([True,False])
        for k in ('readers','token_dirty'):s[k]=np.zeros(2,bool)
        identities={};classes={}
        # Local exact labels preserve identity and partition; not a runtime ID allocator.
        for slot,value,key in rows:
            identity=json.dumps(value,sort_keys=True)
            s['slots'][0,slot]=identities.setdefault(identity,len(identities));s['slot_valid'][0,slot]=True
            if key is not None:s['slot_roots'][0,slot]=classes.setdefault(key,len(classes))
            else:
                s['slot_roots'][0,slot]=s['slots'][0,slot];v=value.get('value')
                supported=isinstance(v,(float,int)) and not isinstance(v,bool) and np.isfinite(v) and abs(v)<=np.finfo(np.float32).max and float(np.float32(v))==v
                if supported:s['scalar_numeric'][0,slot]=True;s['scalar_numbers'][0,slot]=v
                else:s['scalar_codes'][0,slot]=scalar(value);s['scalar_valid'][0,slot]=True
        s['keys'][0,0]=rid
        for j,slot in enumerate(lowered['input_slots'][rid]):s['keys'][0,j+1]=s['slots'][0,slot]
        roles,_=template(recipe['rules'][rid]);s['tokens'][0]=encode(rows,roles,'class-balanced')
        one=dict(lowered,entries=[entry]);plan=tensors(one,np.zeros((1,128,128)),np.zeros((1,128)));plan.pop('weights');plan.pop('bias')
        il,cl=compile_features(recipe,entry);dp,di,dc=map(dev,(plan,il,cl));stage=mx.array(entry['stage'])
        out,marks=mx.compile(lambda state:step(state,dp,di,dc,model,stage,mx))(dev(s));mx.eval(out,marks)
        admitted=bool(np.array(marks['admission']['accepted'])[0]);exact=True
        if admitted:
            expected=[entry['consumer']]+[int(s['slots'][0,i]) if ok else -1 for i,ok in zip(entry['projection'],entry['projection_valid'])]
            exact=np.array_equal(np.array(out['keys'])[1],expected)
        records.append(dict(entry=entry['entry'],producer=rid,consumer=entry['consumer'],admitted=admitted,exact_projected_key=bool(exact),
                            finite=bool(np.isfinite(np.array(out['tokens'])).all()),transferred=bool(np.array(marks['admission']['transferred']).any())))
    result=dict(scope='One captured completed source per supported recipe Entry; GPU continuation, encoding, ridge and admission. Not autonomous Eggcc execution',
        trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),
        lowered_entries=len(lowered['entries']),tested_entries=len(records),admitted=sum(r['admitted'] for r in records),
        passed=bool(records) and all(r['admitted'] and r['exact_projected_key'] and r['finite'] and not r['transferred'] for r in records),records=records,
        limitations=['Source states captured from CPU and locally relabeled; no consumer match list supplied',
                     'One example per Entry is coverage probing, not complete matching or prediction accuracy',
                     'New token prediction is not proof of completed effects or ownership transfer',
                     'No multi-source query, cross-stage closure or whole-workload speed claim'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
