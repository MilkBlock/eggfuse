"""Frozen-model legal-partition audit; all candidates remain speculative."""
import argparse
from collections import defaultdict
import hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from token_eq_readout import examples,readout_rows,materialize,expand_scores,check_partition
from packed_cell_replay import executor,prepare
from select_eq_readout import gpu_read
from audit_training_expansion import verified,summarize
from device_partition_readout import compile_catalog,select


def main():
    p=argparse.ArgumentParser()
    for name in ('trace','model','model_report','weights','selection_report','output'):p.add_argument(name,type=Path)
    a=p.parse_args();mr=json.loads(a.model_report.read_text());sr=json.loads(a.selection_report.read_text())
    model=verified(a.model,mr,'model_sha256');decoder=verified(a.weights,sr,'weights_sha256')
    raw=read_bytes(a.trace);sha=hashlib.sha256(raw).hexdigest()
    if sha!=sr['test_trace_sha256'] or sha!=mr['provenance']['test_trace'] or sr['model_sha256']!=mr['model_sha256']:raise ValueError('provenance mismatch')
    trace=json.loads(raw)
    nodes,rows=examples(trace,int(model['channels']),bool(model['zero_role_channels']),True,str(model['encoding']),bool(model.get('source_neighborhood',False)),bool(model.get('source_relations',False)))
    tokens=np.array(executor(nodes,model['w'],model['coef'],prepare(nodes,'two'),True)())
    x,_=materialize(readout_rows(rows,True),tokens,decoder['w'],True)
    ids=np.flatnonzero(decoder['alphas']==sr['selected']['partition'])
    if len(ids)!=1:raise ValueError('missing selected readout')
    scores,numeric=gpu_read(x,decoder['coef'][:,ids]);scores=scores[:,0]
    output=scores.copy();groups=defaultdict(list);offset=0;plans={};ready=np.zeros(len(rows),bool)
    for i,row in enumerate(rows):
        n=len(row['quotient']['representatives']);groups[row['rule']].append((i,offset,n));offset+=n
    gpu_seconds=0.;numeric_mismatches=0;covered=0;ties=0;storage=0;states=0;dot_products=0
    for rid,group in groups.items():
        plan=compile_catalog(trace['recipe']['rules'][rid],rows[group[0][0]])
        plans[rid]=plan
        if not plan['covered']:continue
        matrix=plan['matrix'];storage+=matrix.nbytes;states+=len(matrix)
        batch=np.array([scores[start:start+n] for _,start,n in group],np.float32)
        dmat=mx.array(matrix);clock=time.monotonic()
        result,marks=mx.compile(lambda x:select(x,dmat,mx))(mx.array(batch));mx.eval(result,marks)
        gpu_seconds+=time.monotonic()-clock
        values=np.array(result);ok=np.array(marks['ready']);ties+=int(np.array(marks['ambiguous']).sum())
        ref,rm=select(batch,matrix,np)
        numeric_mismatches+=int(np.count_nonzero(ref!=values))+int(np.count_nonzero(rm['ready']!=ok))
        covered+=len(group);dot_products+=len(group)*matrix.shape[0]*matrix.shape[1]
        for j,(i,start,n) in enumerate(group):output[start:start+n]=values[j];ready[i]=ok[j]
    errors=0;unmarked_errors=0;checked=0;ready_checked=0;covered_nontransitive=0;clock=time.monotonic();offset=0
    for i,row in enumerate(rows):
        n=len(row['quotient']['representatives'])
        full=expand_scores(row,output[offset:offset+n],True,True);offset+=n
        check=check_partition(row['pairs'],row['y'],full)
        if row['pairs']:
            checked+=1;errors+=int(not check['exact']);unmarked_errors+=int(ready[i] and not check['exact']);ready_checked+=int(ready[i])
            covered_nontransitive+=int(plans[row['rule']]['covered'] and check['nontransitive'])
    cpu_seconds=time.monotonic()-clock
    result=dict(scope='frozen held-out Cell Eq partition projection, not full GPU runtime',trace_sha256=sha,model_sha256=mr['model_sha256'],weights_sha256=sr['weights_sha256'],
        alpha=sr['selected']['partition'],max_classes_per_sort=5,max_states=256,baseline=summarize(rows,scores),projected=summarize(rows,output),
        total_instances=len(rows),covered_instances=covered,explicit_cpu_marks=int((~ready).sum()),ambiguous_instances=ties,
        catalog_bytes=storage,catalog_states=states,projection_multiply_adds=dot_products,gpu_projection_compile_upload_seconds=gpu_seconds,
        cpu_supervision=dict(checked=checked,wrong=errors,error_fraction=errors/max(1,checked),unmarked_checked=ready_checked,wrong_among_unmarked=unmarked_errors,unmarked_error_fraction=unmarked_errors/max(1,ready_checked),covered_nontransitive=covered_nontransitive,seconds=cpu_seconds,
            instances_per_second=checked/cpu_seconds,scope='saved-label Eq comparison only; not native proof replay'),
        numerical_mismatches=numeric_mismatches,readout_numeric=numeric,union_authorized=False,backpropagation=False,
        limitations=['Legal equivalence partitions can still be false; zero marks never proves correctness',
            'Unsupported class/state budgets remain explicit CPU boundaries with original predictions',
            'All model and partition-policy choices frozen before test; no fitting or threshold tuning',
            'Observed successful matches and routes supplied; no ownership transfer or whole Eggcc claim'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if numeric_mismatches or covered_nontransitive:raise SystemExit(1)

if __name__=='__main__':main()
