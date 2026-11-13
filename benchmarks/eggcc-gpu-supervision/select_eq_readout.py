"""Validation-only ridge selection on frozen whole-Cell tokens; no threshold search."""
import argparse
import hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from token_eq_readout import examples,readout_rows,materialize,expand_scores
from audit_training_expansion import summarize,verified
from packed_cell_replay import executor,prepare,audit

ALPHAS=(.1,1.,10.,100.)


def fit_candidates(x,y):
    mean=x.mean(0);mean[0]=0
    scale=np.maximum(x.std(0),.02);scale[0]=1
    z=((x-mean)/scale).astype(np.float64);gram=z.T@z;rhs=z.T@y[:,None].astype(np.float64)
    result=[]
    for alpha in ALPHAS:
        penalty=np.eye(x.shape[1])*alpha;penalty[0,0]=0
        coef=np.linalg.solve(gram+penalty,rhs).astype(np.float32)/scale[:,None]
        coef[0]-=(mean[:,None]*coef).sum(0);result.append(coef)
    return np.concatenate(result,axis=1)


def select(candidates):
    eligible=[i for i,c in enumerate(candidates) if c.get('numerically_eligible',True)]
    if not eligible:raise ValueError('no numerically eligible validation candidate')
    return dict(mse=min(eligible,key=lambda i:(candidates[i]['oracle_mse'],i)),
        partition=min(eligible,key=lambda i:(-candidates[i]['macro_exact_rate'],candidates[i]['macro_false_pair_rate'],i)),
        false_merge=min(eligible,key=lambda i:(candidates[i]['macro_false_pair_rate'],-candidates[i]['macro_exact_rate'],i)))


class NumericReadoutError(ValueError):
    def __init__(self,check):
        self.check=check
        super().__init__('numeric readout disagreement: '+json.dumps(check))


def query_location(rows,index):
    for row in rows:
        ids=row['quotient']['representatives']
        if index<len(ids):return dict(run=row['run'],binding=row['ordinal'],rule=row['rule'],slots=list(row['pairs'][ids[index]]))
        index-=len(ids)
    raise ValueError('query index outside layout')


def gpu_read(matrix,coef,strict=True):
    weight=mx.array(coef);chunks=[]
    for start in range(0,len(matrix),4096):
        out=mx.array(matrix[start:start+4096])@weight;mx.eval(out);chunks.append(np.array(out))
    scores=np.concatenate(chunks);reference=matrix@coef;check=audit(scores,reference)
    check['threshold_disagreements']=int(((scores>=.5)!=(reference>=.5)).sum())
    check['candidates']=[dict(audit(scores[:,j],reference[:,j]),threshold_disagreements=int(((scores[:,j]>=.5)!=(reference[:,j]>=.5)).sum())) for j in range(scores.shape[1])]
    if strict and (not check['passed'] or check['threshold_disagreements']):
        disagreements=np.argwhere((scores>=.5)!=(reference>=.5))
        check['examples']=[dict(query=int(i),candidate=int(j),gpu=float(scores[i,j]),cpu=float(reference[i,j]),
            cpu_f32_operands=float(matrix[i].astype(np.float32).astype(np.float64)@coef[:,j].astype(np.float32).astype(np.float64))) for i,j in disagreements[:8]]
        raise NumericReadoutError(check)
    return scores,check


def main():
    p=argparse.ArgumentParser();p.add_argument('training',type=Path);p.add_argument('validation',type=Path)
    p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('model_report',type=Path)
    p.add_argument('weights',type=Path);p.add_argument('output',type=Path);p.add_argument('--marks',type=Path,required=True);p.add_argument('--reject-unstable-candidates',action='store_true');a=p.parse_args()
    report=json.loads(a.model_report.read_text());model=verified(a.model,report,'model_sha256')
    source_neighborhood=bool(model.get('source_neighborhood',False))
    source_relations=bool(model.get('source_relations',False))
    encoding=str(model.get('encoding','slot'));channels=int(model['channels']);zero=bool(model['zero_role_channels'])
    w=np.random.default_rng(208).normal(0,1/np.sqrt(512),(512,256)).astype(np.float32)
    provenance={};data={};binary=None
    for partition,path in [('train',a.training),('validation',a.validation)]:
        raw=path.read_bytes();manifest=json.loads(raw);provenance[partition]=hashlib.sha256(raw).hexdigest()
        if manifest['partition']!=partition or manifest['manifest_sha256']!=report['provenance']['corpus_manifest']:raise ValueError('partition mismatch')
        if partition=='train' and provenance[partition]!=report['provenance']['train']:raise ValueError('model training mismatch')
        if binary is not None and binary!=manifest['binary_sha256']:raise ValueError('capture binary mismatch')
        binary=manifest['binary_sha256'];data[partition]=[]
        for entry in manifest['cases']:
            if entry['status']!='complete':continue
            raw=read_bytes(Path(entry['trace']))
            if entry['split']!=partition or hashlib.sha256(raw).hexdigest()!=entry['trace_sha256']:raise ValueError('case provenance mismatch')
            trace=json.loads(raw)
            if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture audit missing')
            nodes,rows=examples(trace,channels,zero,True,encoding,source_neighborhood,source_relations)
            data[partition].append((entry['case'],nodes,rows))
    xs=[];ys=[];unique=set()
    for _,nodes,rows in data['train']:
        chosen=[]
        for row in rows:
            key=(row['node']['family'],row['node']['state_key'])
            if key not in unique:unique.add(key);chosen.append(row)
        x,y=materialize(readout_rows(chosen,True),np.array([n['target'] for n in nodes]),w,True);xs.append(x);ys.append(y)
    clock=time.monotonic();coef=fit_candidates(np.concatenate(xs),np.concatenate(ys));fit_seconds=time.monotonic()-clock
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);candidates=[dict(alpha=alpha,workloads={},numerically_eligible=True) for alpha in ALPHAS];numeric={}
    mse_sum=np.zeros(len(ALPHAS));mse_count=0;unique_val=set()
    for case,nodes,rows in data['validation']:
        target=np.array([n['target'] for n in nodes]);chosen=[]
        for row in rows:
            key=(row['node']['family'],row['node']['state_key'])
            if key not in unique_val:unique_val.add(key);chosen.append(row)
        x,y=materialize(readout_rows(chosen,True),target,w,True)
        mse_sum+=np.square(x@coef-y[:,None]).sum(0);mse_count+=len(y)
        predicted=np.array(executor(nodes,model['w'],model['coef'],prepare(nodes,'two'),True)())
        x,_=materialize(readout_rows(rows,True),predicted,w,True)
        try:scores,numeric[case]=gpu_read(x,coef,strict=not a.reject_unstable_candidates)
        except NumericReadoutError as error:
            error.check['case']=case
            for example in error.check.get('examples',[]):
                example.update(query_location(rows,example['query']),alpha=ALPHAS[example['candidate']])
            raise NumericReadoutError(error.check) from error
        for i,candidate in enumerate(candidates):
            check=numeric[case]['candidates'][i]
            candidate['numerically_eligible'] &= check['passed'] and not check['threshold_disagreements']
            result=summarize(rows,scores[:,i]);result['pairs']=sum(len(r['pairs']) for r in rows)
            candidate['workloads'][case]=result
    for i,candidate in enumerate(candidates):
        cases=list(candidate['workloads'].values());candidate['oracle_mse']=float(mse_sum[i]/mse_count)
        candidate['macro_exact_rate']=float(np.mean([r['exact_partitions']/r['query_instances'] for r in cases]))
        candidate['macro_false_pair_rate']=float(np.mean([r['false_merges']/r['pairs'] for r in cases]))
    selected=select(candidates)
    # Selection is complete before loading test labels or evaluating test tokens.
    with a.weights.open('wb') as f:np.savez_compressed(f,w=w,coef=coef,alphas=ALPHAS)
    raw=read_bytes(a.trace);trace_sha=hashlib.sha256(raw).hexdigest()
    if trace_sha!=report['provenance']['test_trace']:raise ValueError('test trace mismatch')
    nodes,rows=examples(json.loads(raw),channels,zero,True,encoding,source_neighborhood,source_relations)
    predicted=np.array(executor(nodes,model['w'],model['coef'],prepare(nodes,'two'),True)())
    clock=time.monotonic();matrix,_=materialize(readout_rows(rows,True),predicted,w,True);encoding_seconds=time.monotonic()-clock
    indices=sorted(set(selected.values()));clock=time.monotonic();scores,test_numeric=gpu_read(matrix,coef[:,indices]);read_seconds=time.monotonic()-clock
    results={};marks=0;clock=time.monotonic()
    with a.marks.open('w') as out:
        for policy,index in selected.items():
            values=scores[:,indices.index(index)];results[policy]=dict(alpha=ALPHAS[index],**summarize(rows,values));offset=0
            for row in rows:
                count=len(row['quotient']['representatives']);full=expand_scores(row,values[offset:offset+count],True,True);offset+=count
                errors=[dict(slots=list(pair),predicted_equal=bool(score>=.5),expected_equal=bool(y)) for pair,score,y in zip(row['pairs'],full,row['y']) if (score>=.5)!=y]
                if errors:
                    out.write(json.dumps(dict(policy=policy,run=row['run'],binding=row['ordinal'],rule=row['rule'],errors=errors,union_authorized=False))+'\n');marks+=1
    audit_seconds=time.monotonic()-clock
    result=dict(scope='validation-selected Eq boundary readout for frozen Cell model',provenance=provenance,
        model_sha256=report['model_sha256'],test_trace_sha256=trace_sha,weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),
        candidates=candidates,selected={k:ALPHAS[v] for k,v in selected.items()},test=results,
        unique_train_states=len(unique),unique_validation_states=len(unique_val),fit_seconds=fit_seconds,
        numerical_audits=numeric,test_numerical_audit=test_numeric,local_marks=marks,marks_sha256=hashlib.sha256(a.marks.read_bytes()).hexdigest(),
        test_feature_encoding_seconds=encoding_seconds,test_gpu_readout_seconds=read_seconds,test_audit_and_marks_seconds=audit_seconds,
        reject_unstable_candidates=a.reject_unstable_candidates,threshold=.5,backpropagation=False,union_authorized=False,
        limitations=['Static class Eq audit only, not native correctness or full token state',
            'Oracle-state MSE and predicted-state partition criteria are distinct explicit policies',
            'One fixed token model; validation expansion does not refit its weights',
            'Test outputs do not select policy; all validation-selected policies are reported'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
