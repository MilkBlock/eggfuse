"""Independent full source-Run audit; not replay of selected GPU proposals.

The expected graph is returned for the supervisor's next verified Run only.
No expected binding or effect value is written into GPU state.
"""
from copy import deepcopy
import time
import numpy as np
from reference_cell_closure import facts_from_cells
from reference_union_family import compare_graph


def execute_and_audit(local,reference,rules,state,roots,next_id,frames,model,head,seed_count,attempts,context_depth=0):
    if context_depth not in (0,1,2):raise ValueError('unsupported source context depth')
    import mlx.core as mx
    from audit_snapshot_queries import device
    from device_slot_owners import shape
    from neural_device_candidates import compile_candidates
    from device_neural_speculation import compile_frame
    from device_neural_run import execute
    width=shape(state)[1];eq_width=max(len(r['slots']) for r in rules)
    atoms=max(len(r['query']) for r in rules);fields=max(len(a['args']) for r in rules for a in r['query'])
    offset=len(local['rules'])-len(rules)
    if local['rules'][offset:]!=rules:raise ValueError('Run rules do not match local rule IDs')
    if context_depth:
        from device_witness_context import initialize
        state=initialize(state,atoms,mx)
    plans=[]
    for i,r in enumerate(rules):
        query=device(compile_candidates(local,r,atoms=atoms,fields=fields,compact_constants=True))
        frame=compile_frame(r,width,eq_width,local,True)
        for site in frame['witness_sites'].values():site['context_depth']=context_depth
        plans.append((offset+i,query,frame))
    out,rr,nn,execution=execute(state,roots,next_id,frames,plans,model,head,attempts,mx)
    _,verdict=audit(local,reference,rules,out,rr,nn,seed_count,execution)
    return verdict


def audit(local,reference,rules,state,roots,next_id,seed_count,execution):
    started=time.perf_counter();expected=deepcopy(reference)
    constructions=expected.constructions;unions=expected.unions
    _,matches=expected.apply(rules)
    host={k:np.array(v) for k,v in state.items()}
    facts,covered=facts_from_cells(local,host)
    graph=compare_graph(expected,facts,np.array(roots)[:int(next_id)],seed_count)
    exhausted=bool(execution['query_exhausted']);attention=bool(execution['needs_attention'])
    budget=bool(execution['attempt_budget_exhausted'])
    passed=covered and graph['passed'] and exhausted and not attention and not budget
    attention_events=[]
    for rid,event in execution['trace']:
        if bool(event['needs_attention']):
            flags=('query_incomplete','dirty_input','nonfinite','invalid_keys','rejected_proposal','capacity','payload_invalid','token_refresh_required','stale_witness_context')
            attention_events.append(dict(rule_id=rid,reasons=[k for k in flags if bool(event[k])]))
    return expected,dict(scope='independent CPU source-Run semantic audit; no GPU corrections',
        status='pass' if passed else 'difference',run_done=passed,
        run_changed=passed and (expected.constructions!=constructions or expected.unions!=unions),
        reference_matches=matches,reference_new_constructors=expected.constructions-constructions,
        reference_new_unions=expected.unions-unions,admitted=int(execution['admitted']),
        graph=graph,facts_decoded=covered,query_exhausted=exhausted,needs_attention=attention,
        attention_events=attention_events,
        attempt_budget_exhausted=budget,cpu_audit_seconds=time.perf_counter()-started)
