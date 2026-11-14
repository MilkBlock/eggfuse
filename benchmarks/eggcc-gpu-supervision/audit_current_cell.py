"""Independent multi-Run audit of current-state neural Cell generation.

Synthetic exact initial Cells; no CPU corrections feed subsequent GPU Runs.
Stops a case at its first failed full-Run audit.
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_snapshot_queries import device
from device_stage_models import select_ruleset
from neural_cell_samples import samples
from neural_cell_chains import chains
from audit_neural_gpu_rhs import initial_case
from device_constructor_completion import complete
from neural_owner_handoff import handoff
from neural_device_candidates import compile_frames,compile_candidates
from device_neural_speculation import compile_frame
from device_neural_run import execute
from audit_neural_run import audit,diagnose
from reference_cell_closure import facts_from_cells
from reference_union_family import compare_graph
from train_current_cell import CurrentCellModel


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('weights',type=Path)
    p.add_argument('output',type=Path);p.add_argument('--runs',type=int,default=3)
    p.add_argument('--candidate-capacity',type=int,default=16);p.add_argument('--pair',type=int,nargs=2);p.add_argument('--limit',type=int,default=61);p.add_argument('--attempts',type=int,default=8)
    a=p.parse_args()
    if min(a.runs,a.limit,a.attempts,a.candidate_capacity)<1:raise ValueError('positive budgets required')
    raw=json.loads(a.trace.read_text());recipe,stage=select_ruleset(raw.get('recipe',raw),'canon')
    recipe_hash=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    manifest=json.loads(a.weights.with_suffix('.json').read_text())
    if manifest['recipe_sha256']!=recipe_hash:raise ValueError('checkpoint recipe mismatch')
    records=[];base=samples(recipe,1,23001,records,ordered=True);transfers=[]
    chain,_=chains(recipe,records,ordered=True,transfers=transfers,include_uncovered_transfers=True)
    slots=max(len(r['slots']) for r in recipe['rules']);atoms=base['x'].shape[1];fields=base['x'].shape[-1]//128
    model=CurrentCellModel(manifest['input_width'],base['relations'].shape[-1],slots)
    model.load_weights(str(a.weights));selected=[];seen=set()
    for record in transfers:
        i=record['chain'];pair=(int(chain['producer'][i]),int(chain['consumer'][i]))
        if pair not in seen:seen.add(pair);selected.append((pair,record))
    if a.pair is not None:selected=[x for x in selected if x[0]==tuple(a.pair)]
    if not selected:raise ValueError('no selected template pair')
    reports=[]
    for pair,record in selected[:a.limit]:
        local,host,cp,ctx,tp,src,dst,seed_count,reference=initial_case(recipe,record,
            spare=a.runs*a.attempts*len(recipe['rules']),payload_width=2*slots)
        local=dict(local,rules=local['rules']+recipe['rules'])
        state=device(host);registry=device(ctx);next_id=mx.array(seed_count);settled=mx.array(True)
        for _ in range(2):
            state,next_id,marks=complete(state,device(cp),next_id,mx.array(len(ctx['roots'])),mx.array(64),
                mx.array(True),settled,mx,registry,eq_rounds=8)
            registry=marks['eq_context'];settled=marks['eq_settled']
        if bool(marks['needs_attention']):raise ValueError('unsettled initial state')
        if tp['covered']:
            state,_=handoff(state,device(tp),mx.array(src),mx.array(dst),mx.array(1),mx.array(1),
                mx.array(1.),mx.zeros(128),mx.array(True),mx.array(True),mx)
        roots=registry['roots'];width=host['owner_projection'].shape[1]
        frames=device(compile_frames(local,width));offset=len(local['rules'])-len(recipe['rules'])
        from device_witness_context import initialize
        state=initialize(state,atoms,mx)
        plans=[]
        for i,r in enumerate(recipe['rules']):
            query=device(compile_candidates(local,r,atoms=atoms,fields=fields,compact_constants=True,capacity=a.candidate_capacity))
            frame=compile_frame(r,width,slots,local,True)
            for site in frame['witness_sites'].values():site['context_depth']=1
            plans.append((offset+i,query,frame))
        results=[]
        for run in range(a.runs):
            facts,covered=facts_from_cells(local,{k:np.array(v) for k,v in state.items()})
            check=compare_graph(reference,facts,np.array(roots)[:int(next_id)],seed_count,include_mapping=True)
            if not covered or not check['passed']:raise ValueError('invalid audited input state')
            # Ensure success cannot be attributed to old recurrent embeddings.
            state=dict(state,tokens=mx.full_like(state['tokens'],float('nan')))
            state,roots,next_id,execution=execute(state,roots,next_id,frames,plans,model,model.eq,a.attempts,mx,capture=True)
            expected,verdict=audit(local,reference,recipe['rules'],state,roots,next_id,seed_count,execution)
            verdict['admission_diagnosis']=diagnose(local,reference,execution,check['mapping'],slots)
            results.append(verdict)
            if verdict['status']!='pass':break
            reference=expected
            if not verdict['run_changed']:break
        reports.append(dict(pair=pair,runs=results))
        print(json.dumps(dict(pair=pair,runs=len(results),status=results[-1]['status'])),flush=True)
    result=dict(scope='standalone synthetic canon multi-Run GPU audit; exact initial Cells, no CPU corrections',
        recipe_sha256=recipe_hash,weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),
        stage=stage,run_budget=a.runs,attempts=a.attempts,candidate_capacity=a.candidate_capacity,cases=reports,
        first_run_pass=sum(x['runs'][0]['status']=='pass' for x in reports),
        verified_fixedpoints=sum(x['runs'][-1]['status']=='pass' and not x['runs'][-1]['run_changed'] for x in reports))
    a.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
