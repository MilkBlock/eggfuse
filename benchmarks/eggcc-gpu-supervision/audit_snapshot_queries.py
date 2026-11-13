"""Real visible Eggcc snapshot -> GPU matches, ridge tokens and owner evidence."""
import argparse,json,hashlib,time
from collections import Counter
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from device_snapshot_import import prepare,reference_keys
from device_query_join import compile_query
from device_join_transition import compile_transition,step
from device_matched_takeover import compile_catalog,initialize
from device_slot_owners import pack


def device(value):
    if isinstance(value,np.ndarray):return mx.array(value)
    if isinstance(value,dict):return {k:device(v) for k,v in value.items()}
    if isinstance(value,list):return [device(v) for v in value]
    if isinstance(value,tuple):return tuple(device(v) for v in value)
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--max-source-rows',type=int,default=32);p.add_argument('--capacity',type=int,default=32);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw)
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture audit missing')
    with np.load(a.model) as saved:
        if str(saved['encoding'])!='class-history-neighborhood-input' or int(saved['channels'])!=4:raise ValueError('model interface mismatch')
        if bool(saved.get('source_neighborhood',False)) or bool(saved.get('source_relations',False)):raise ValueError('unsupported source context')
        model=device({k:saved[k] for k in ('w','coef')})
    mx.set_default_device(mx.gpu);recipe=trace['recipe'];snapshot=trace['final'];views={};skips=Counter();records=[]
    counts=Counter(r['table'] for r in snapshot['rows'] if not r['subsumed'])
    for rid,rule in enumerate(recipe['rules']):
        query=compile_query(recipe,rid,views)
        if not query['covered'] or not query['atoms']:skips['unsupported_query']+=1;continue
        tables={atom['call']['table'] for atom in rule['query']};size=sum(counts[t] for t in tables)
        if not size or any(not counts[t] for t in tables):skips['empty_input_table']+=1;continue
        if size>a.max_source_rows:skips['source_row_budget']+=1;continue
        start=time.monotonic();local,state,ids,rows=prepare(recipe,snapshot,rid,a.capacity)
        plan=compile_transition(local,0);blocks,catalog,atoms=compile_catalog(local,[(0,plan)],state['slots'].shape[1])
        packed=initialize(pack(state),atoms);dp=device(blocks[0][1]);ds=device(packed)
        preparation=time.monotonic()-start;start=time.monotonic()
        out,marks=mx.compile(lambda s:step(s,dp,model,a.capacity,mx.array(True),mx.array(True),mx))(ds);mx.eval(out,marks)
        gpu_seconds=time.monotonic()-start
        start=time.monotonic();keys=np.array(out['keys']);present=np.array(out['present']);actual={tuple(k) for k in keys[present&(keys[:,0]==0)]}
        expected=reference_keys(rule,rows,ids,keys.shape[1]);overflow=bool(marks['overflow'])
        complete=bool(marks['query_complete']);passed=actual<=expected and (actual==expected if complete else True)
        finite=bool(np.isfinite(np.array(out['tokens'])).all());passed &= finite
        evidence=int(np.count_nonzero(np.array(out['takeover_plan'])>=0));pending=int(np.count_nonzero(present&~np.array(out['settled'])))
        cpu_seconds=time.monotonic()-start
        records.append(dict(rule=rid,source_rows=len(rows),atoms=len(query['atoms']),expected=len(expected),generated=len(actual),query_complete=complete,overflow=overflow,
            passed=passed,finite=finite,missing=len(expected-actual),extra=len(actual-expected),pending_effect_cells=pending,takeover_hints=evidence,compiled_takeover_plans=len(catalog),
            evidence_bytes=sum(v.nbytes for k,v in packed.items() if k.startswith('takeover_')),candidate_lanes=int(marks['candidate_lanes']),
            input_preparation_seconds=preparation,gpu_compile_upload_match_infer_admit_seconds=gpu_seconds,cpu_raw_join_and_comparison_seconds=cpu_seconds))
    result=dict(scope='real final-snapshot local query initialization and GPU admission; not initial-program multi-stage execution',
        trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),max_source_rows=a.max_source_rows,capacity=a.capacity,
        rules=len(recipe['rules']),tested=len(records),skipped=dict(skips),passed=bool(records) and all(r['passed'] for r in records),
        generated=sum(r['generated'] for r in records),expected=sum(r['expected'] for r in records),complete_queries=sum(r['query_complete'] for r in records),
        cpu_detected_extra=sum(r['extra'] for r in records),cpu_detected_missing=sum(r['missing'] for r in records),pending_effect_cells=sum(r['pending_effect_cells'] for r in records),
        takeover_hints=sum(r['takeover_hints'] for r in records),committed_rhs_mutations=0,physical_takeovers=0,backpropagation=False,records=records,
        limitations=['Visible seed facts come from final exports, not program initialization; no future consumer matches are supplied',
            'Local exact integer IDs preserve typed canonical snapshot identities; they do not reconstruct historical stable IDs',
            'Seed templates differ from training producer templates; token accuracy is not established',
            'Only queried constructor tables are imported; broader effects and external closure remain CPU obligations',
            'Pending effects prevent ownership takeover; matched tokens are not committed mutations',
            'CPU timing is raw-value join/check and includes output readback; GPU timing includes compilation/upload; no speed ratio'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
