"""Real-snapshot supported RHS and automatic physical-owner takeover audit."""
import argparse,hashlib,json,time
from collections import Counter
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from device_snapshot_import import prepare,reference_keys,identity
from device_query_join import compile_query
from device_join_transition import compile_transition,step
from device_constructor_completion import compile_completion,complete
from device_matched_takeover import compile_catalog,initialize,finish
from device_slot_owners import pack,read
from audit_snapshot_queries import device


def expected_slots(rule,key,rows,ids):
    lookup={}
    for row in rows:
        fields=[ids[identity(v)] for v in row['values']]
        address=(row['table'],tuple(fields[:-1]))
        if address in lookup and lookup[address]!=fields[-1]:raise ValueError('conflicting snapshot constructor')
        lookup[address]=fields[-1]
    slots={i:value for i,value in zip((i for i,s in enumerate(rule['slots']) if s['definition']=='query'),key[1:])}
    for op in rule['effects']:
        if op['kind']=='copy':slots[op['dst']]=slots[op['arg']['slot']]
        else:
            address=(op['call']['table'],tuple(slots[a['slot']] for a in op['args']))
            if address not in lookup:return None
            slots[op['dst']]=lookup[address]
    return slots


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--max-source-rows',type=int,default=32);p.add_argument('--capacity',type=int,default=32);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw);recipe=trace['recipe'];snapshot=trace['final']
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture audit missing')
    with np.load(a.model) as saved:
        if str(saved['encoding'])!='class-history-neighborhood-input' or int(saved['channels'])!=4 or bool(saved.get('source_neighborhood',False)) or bool(saved.get('source_relations',False)):raise ValueError('model interface mismatch')
        model=device({k:saved[k] for k in ('w','coef')})
    mx.set_default_device(mx.gpu);views={};skips=Counter();records=[]
    for rid,rule in enumerate(recipe['rules']):
        query=compile_query(recipe,rid,views)
        if not query['covered'] or not query['atoms']:skips['unsupported_query']+=1;continue
        try:local,state,ids,rows=prepare(recipe,snapshot,rid,a.capacity,include_effects=True)
        except ValueError as e:skips[str(e)]+=1;continue
        if len(rows)>a.max_source_rows:skips['source_row_budget']+=1;continue
        # Empty queried tables are a legitimate zero result, but not an execution test.
        if any(not any(row['table']==q['call']['table'] for row in rows) for q in rule['query']):skips['empty_query_table']+=1;continue
        blocks,catalog,atoms=compile_catalog(local,[(0,compile_transition(local,0))],state['slots'].shape[1])
        packed=initialize(pack(state),atoms);dp=device(blocks[0][1]);cp=device(compile_completion(local,state['slots'].shape[1]));ds=device(packed)
        top=len(ids)
        def flow(s):
            admitted,q=step(s,dp,model,a.capacity,mx.array(True),mx.array(True),mx)
            completed,next_id,e=complete(admitted,cp,mx.array(top),mx.array(top+a.capacity*max(1,len(rule['effects']))),mx.array(a.capacity),mx.array(True),mx.array(True),mx)
            # An incomplete query cannot commit a partial source Run's effects.
            candidate={k:mx.where(q['query_complete'],completed[k],v) for k,v in admitted.items()}
            boundary=q['query_complete']&~e['needs_attention']
            out,t=finish(candidate,catalog,boundary,mx,budget=a.capacity,diagnostics=True)
            return out,q,e,t,mx.where(q['query_complete'],next_id,top)
        start=time.monotonic();out,q,e,t,next_id=mx.compile(flow)(ds);mx.eval(out,q,e,t,next_id);gpu=time.monotonic()-start
        start=time.monotonic();final={k:np.array(v) for k,v in out.items()};live=final['present']&(final['keys'][:,0]==0)
        expected=reference_keys(rule,rows,ids,state['keys'].shape[1]);actual={tuple(k) for k in final['keys'][live]};covered=bool(q['query_complete'])
        wrong=0;unknown=0;checked=0
        for index in np.flatnonzero(live&final['settled']):
            values=expected_slots(rule,final['keys'][index],rows,ids)
            if values is None:unknown+=1;continue
            checked+=1;slots=np.array(list(values),np.int32)
            got=read(final,'slots',np.array(index),slots,np);valid=read(final,'slot_valid',np.array(index),slots,np)
            wrong+=int(not (valid.all() and np.array_equal(got,list(values.values()))))
        # Every imported source remains readable after relocation.
        source_corrupt=0
        for index in range(len(rows)):
            valid=state['slot_valid'][index];positions=np.arange(valid.size)
            intact=read(final,'slot_valid',np.array(index),positions,np)[valid].all()
            for column in ('slots','slot_roots','scalar_numbers','scalar_numeric','scalar_codes','scalar_valid'):
                got=read(final,column,np.array(index),positions,np)
                intact=bool(intact) and np.array_equal(got[valid],state[column][index,valid])
            source_corrupt+=int(not intact)
        passed=actual<=expected and (actual==expected if covered else True) and wrong==0 and unknown==0 and source_corrupt==0
        records.append(dict(rule=rid,source_rows=len(rows),generated=len(actual),expected=len(expected),cpu_missing=len(expected-actual),cpu_extra=len(actual-expected),query_complete=covered,query_overflow=bool(q['overflow']),
            completed=int(np.count_nonzero(live&final['settled'])),pending=int(np.count_nonzero(live&~final['settled'])),cpu_checked=checked,cpu_wrong=wrong,cpu_unknown=unknown,source_corrupt=source_corrupt,
            released=int(t['released']),takeover_attempted=int(t['attempted']),takeover_blocked=int(t['blocked']),copied_fields=int(t['copied_fields']),
            blocked_reasons={k:int(v) for k,v in t['blocked_reasons'].items()},
            live_owners=int(final['owner_live'].sum()),logical_cells=int(final['present'].sum()),retained_hints=int(np.count_nonzero(final['takeover_plan']>=0)),
            fresh_constructor_ids=int(next_id)-top,effects_executed=int(e['executed']) if covered else 0,needs_attention=not covered or bool(e['needs_attention']),
            gpu_compile_upload_seconds=gpu,cpu_check_seconds=time.monotonic()-start,passed=passed))
        print(json.dumps(records[-1]),flush=True)
    result=dict(scope='real final-snapshot local supported RHS plus matched-owner transfer; not full Eggcc execution',trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),
        max_source_rows=a.max_source_rows,capacity=a.capacity,skipped=dict(skips),tested=len(records),passed=bool(records) and all(r['passed'] for r in records),
        totals={k:sum(r[k] for r in records) for k in ('generated','expected','cpu_missing','cpu_extra','completed','pending','cpu_checked','cpu_wrong','cpu_unknown','source_corrupt','released','takeover_attempted','takeover_blocked','effects_executed','fresh_constructor_ids')},records=records,
        limitations=['Canonical final snapshot is the input, not program initialization', 'Query/RHS constructor tables are fully imported; hidden reuse, other effects and global repair are rejected',
            'Closed-world seeded lookup plus GPU exact effects, not a trained proof of completion', 'Token inference accuracy and whole multi-stage lifetime semantics remain unproved',
            'CPU check compares actual returned identities against raw snapshot facts; no native proof replay or speedup claim'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
