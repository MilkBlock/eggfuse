"""CPU replay for the two-row credit experiment and independent reward oracle."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.append(str(HERE.parent))
from eclass_ablation.data import audit as audit_source, dataset
from eclass_ablation.data.check import discrete
from eclass_ablation.data.runtime import CORPUS
from width_ablation.audit import load_trace,paired_layouts


def numpy_reward(data,first,second,report=None):
    """Rebuild terminal rewards from CPU source semantics and actual generated slots.

    Gold target arrays are never read here; local guards use certified state,
    and external equality uses the real CPU replay. A pointer to the wrong
    active parent cannot be repaired by its payload or the desired label.
    """
    report=audit_source(data,first,second) if report is None else report
    n=len(data['a']);parts={}
    for key,stage in [('run1',first),('run2',second)]:
        r=report[key]['per_graph']
        def field(name):return np.array([g[name] for g in r],dtype=np.int32)
        obligations=field('obligations');active=field('active_outputs');correct=obligations-field('semantic_missing')
        # A correct binding with an incorrect row remains a semantic omission.
        values=dict(obligations=obligations,active_outputs=active,valid_unique=field('valid_unique'),
                    unique_correct=correct,missing=field('missing'),semantic_missing=field('semantic_missing'),
                    duplicates=field('duplicates'),illegal=field('illegal'),waste=active-correct,
                    complete=field('complete').astype(bool),coverage=correct/np.maximum(obligations,1))
        parts.update({key+'_'+name:v for name,v in values.items()})
    required=[];used=[]
    for g in range(n):
        a,b,requests=(data[k][g] for k in ('a','b','requests'))
        def graph(stage):return {k:stage[k][g] for k in ('active','pointers','rows')}
        original={(int(a[i,0]),int(a[i,1])):(i,j) for i in range(len(a)) for j in range(len(b)) if a[i,0]==b[j,0]}
        legal=report['request_legal'][g]
        needed={original[tuple(map(int,r[2:4]))] for r,ok in zip(requests,legal) if ok}
        actual={}
        for slot,(i,j),row in discrete(graph(first)):
            if (0<=i<len(a) and 0<=j<len(b) and a[i,0]==b[j,0]
                    and row==tuple(map(int,[*a[i],b[j,1]]))):actual[slot]=((i,j),row)
        consumed=set()
        for _,(pi,ri),row in discrete(graph(second)):
            if pi not in actual or not 0<=ri<len(requests) or not legal[ri]:continue
            identity,parent=actual[pi];request=requests[ri];wanted=tuple(map(int,request[2:4]))
            if parent[:2]==wanted and row==(*wanted,int(request[4]),parent[3],parent[4]):consumed.add(identity)
        required.append(len(needed));used.append(len(consumed))
    needed=np.array(required,dtype=np.int32);used=np.array(used,dtype=np.int32)
    ready=np.array([g['unavailable_parent_obligations'] for g in report['run2']['per_graph']],dtype=np.int32)
    exact=parts['run2_complete'] & (parts['run2_obligations']>0)
    p=used/np.maximum(1,needed);c1,c2=parts['run1_coverage'],parts['run2_coverage']
    w1=parts['run1_waste']/first['active'].shape[1];w2=parts['run2_waste']/second['active'].shape[1]
    parts.update(required_parents=needed,consumed_parents=used,consumed_parent_fraction=p,
                 unavailable_parent_obligations=ready,parent_ready=ready==0,exact_nonempty_finish=exact,
                 C1=c1,C2=c2,P=p,E2=exact.astype(np.float32),W1=w1,W2=w2)
    score=(c1+2*c2+p+exact-w1-w2-1)/4
    return score,parts


def file_hash(path):return sha256(path.read_bytes()).hexdigest()


def sampled_rewards(root):
    templates={t['id']:t for t in json.loads((CORPUS/'manifest.json').read_text())['templates'] if t['split']=='train'}
    train={};results={};input_hash={};first_actions={}
    for seed in (1703,1709):
        for arm in ('team','counterfactual'):
            folder=root/f'{arm}-{seed}';fit=json.loads((folder/'fit.json').read_text());records={}
            if fit['arm']!=arm or fit['seed']!=seed or fit['steps']!=1024:raise ValueError('sampled training metadata mismatch')
            for step in (1,1024):
                path=folder/f'sampled-{step}.npz'
                with np.load(path,allow_pickle=False) as z:
                    tid=str(z['template'].item());index=z['indices']
                    if tid not in train:train[tid]=dataset('train',templates[tid])
                    if index.dtype.kind not in 'iu' or index.shape!=(32,) or (index<0).any() or (index>=len(train[tid]['a'])).any():
                        raise ValueError('invalid training graph indices')
                    d={k:(v[index] if isinstance(v,np.ndarray) else v) for k,v in train[tid].items()}
                    one,two=[{k:z[f'{i}_{k}'] for k in ('active','pointers','rows')} for i in (0,1)]
                    token=z['token'];g=np.arange(len(index))[:,None]
                    li,ri=one['pointers'].transpose(2,0,1);pi,qi=two['pointers'].transpose(2,0,1)
                    if len(token)!=32 or token.shape[1:]!=(8,56) or not np.isfinite(token).all():raise ValueError('invalid generated training token')
                    for ids,bound in ((li,6),(ri,2),(pi,8),(qi,4)):
                        if (ids<0).any() or (ids>=bound).any():raise ValueError('invalid sampled pointer')
                    for offset,width,ids in ((32,2,one['active']),(34,8,li),(42,8,ri)):
                        np.testing.assert_array_equal(token[...,offset:offset+width],np.eye(width)[ids])
                    rows=np.concatenate((d['a'][g,li],d['b'][g,ri,1,None]),-1)
                    np.testing.assert_array_equal(token[...,50:55],rows);np.testing.assert_array_equal(one['rows'],rows)
                    np.testing.assert_array_equal(token[...,55],d['a_port'][g,li]);selected=token[g,pi,50:55]
                    np.testing.assert_array_equal(two['rows'],np.concatenate((selected[...,:2],d['requests'][g,qi,4,None],selected[...,3:]),-1))
                    check,parts=numpy_reward(d,one,two);errors={}
                    for key,expected in [('reward',check),*[(k,parts[k]) for k in ('C1','C2','P','E2','W1','W2')]]:
                        actual=z[key]
                        if actual.shape!=(32,) or not np.isfinite(actual).all():raise ValueError(f'invalid {key}')
                        np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-7,err_msg=f'{arm}/{seed}/{step}/{key}')
                        if key in ('E2','W1','W2'):np.testing.assert_array_equal(actual,expected)
                        errors[key]=float(np.max(np.abs(actual-expected)))
                    history=next(item for item in fit['history'] if item['step']==step)
                    np.testing.assert_allclose(history['reward'],z['reward'].mean(),rtol=0,atol=2e-7)
                    source_hash=sha256(tid.encode()+index.tobytes()+b''.join(d[k].tobytes() for k in ('a','b','requests','target1','target2'))).hexdigest()
                    peer=(seed,step)
                    if peer in input_hash:assert source_hash==input_hash[peer]
                    input_hash[peer]=source_hash
                    if step==1:
                        digest=sha256(b''.join(v.tobytes() for stage in (one,two) for v in stage.values())).hexdigest()
                        if seed in first_actions and first_actions[seed]!=digest:raise ValueError('paired arms differ on first sampled actions')
                        first_actions[seed]=digest
                    records[str(step)]=dict(template=tid,graphs=len(index),source_sha256=source_hash,
                                            sampled_sha256=file_hash(path),max_absolute_error=errors,
                                            cpu_reward_mean=float(check.mean()),cpu_reward_by_graph=check.tolist())
            results[folder.name]=records
    return results


def replay(root):
    from credit_inputs import fresh_panel, array_digest
    path=root/'results.json';result=json.loads(path.read_text());panels={};comparisons={};common={};hashes={};retention_hashes={};retention={}
    templates={t['id']:t for t in json.loads((CORPUS/'manifest.json').read_text())['templates'] if t['split']=='heldout'}
    labels=set(result['panels'][next(iter(templates))]);expected={f'{arm}-{seed}' for arm in ('frozen1','zero','supervised','team','counterfactual') for seed in (1703,1709)}
    if labels!=expected:raise ValueError('expected all five arms for both seeds')
    for tid,t in templates.items():
        data=fresh_panel(t)
        if array_digest(data)!=result['frozen_inputs']['panels'][tid]['digest']:
            raise ValueError(f'{tid}: fresh panel bytes changed')
        panels[tid]={};raw_metrics={};comparisons[tid]={};common[tid]={}
        for label in sorted(expected):
            width=1 if label.startswith('frozen1-') else 2
            trace=root/'traces'/f'{tid}-{label}.npz';hashes[trace.name]=file_hash(trace)
            if result['trace_sha256'][trace.name]!=hashes[trace.name]:raise ValueError('recorded trace hash mismatch')
            stats=load_trace(trace,data,width);raw_metrics[label]=stats;stored=result['panels'][tid][label]
            for tag,sk in [('run1','r1'),('run2','r2')]:
                for key,value in stored[sk].items():
                    if isinstance(value,(int,bool)) and stats[tag][key]!=value:raise ValueError(f'{tid}/{label}/{sk}/{key}')
            assert stored['complete_by_graph']==[int(g['complete']) for g in stats['run2']['per_graph']]
            assert stored['parent_ready']==[int(g['parent_ready']) for g in stats['run2']['per_graph']]
            assert stored['both_complete_graphs']==stats['both_complete_graphs'] and stored['origin_switch']==stats['origin_switch']
            if 'paired_controls' in stored:assert stored['paired_controls']==stats['paired_controls']
            subset_masks={'blind':data['blind'].astype(bool),'targeted':data['blind']==0}
            for idx,state in enumerate(('pre','post','nonmerge','external')):
                mask=data['state']==idx;subset_masks.update({state:mask,'blind_'+state:mask&subset_masks['blind'],'targeted_'+state:mask&subset_masks['targeted']})
            if set(subset_masks)!=set(stored['strata']):raise ValueError('source strata changed')
            for stratum,mask in subset_masks.items():
                selected=[row for row,keep in zip(stats['run2']['per_graph'],mask) if keep]
                for key,expected_value in stored['strata'][stratum].items():
                    if key=='graphs':observed=len(selected)
                    elif key=='nonempty_complete':observed=sum(bool(row['complete'] and row['nonempty']) for row in selected)
                    elif key=='ready_nonempty':observed=sum(bool(row['parent_ready'] and row['nonempty']) for row in selected)
                    else:observed=sum(int(row[key]) for row in selected)
                    if observed!=expected_value:raise ValueError(f'{tid}/{label}/{stratum}/{key} differs')
            with np.load(trace,allow_pickle=False) as z:
                first,second=[{k:z[f'{i}_{k}'] for k in ('active','pointers','rows')} for i in (0,1)]
                score,parts=numpy_reward(data,first,second,stats)
            panels[tid][label]=dict(graphs=len(score),mean_reward=float(score.mean()),min_reward=float(score.min()),
                max_reward=float(score.max()),reward_by_graph=score.tolist(),
                components={key:float(value.mean()) for key,value in parts.items()},
                complete_nonempty=stats['run2']['nonempty_complete_graphs'],wrong_origin=stats['run2']['wrong_parent'],
                duplicates=stats['run2']['duplicates'],missing=stats['run2']['missing'],origin_switch=stats['origin_switch'])
        for seed in (1703,1709):
            train_arms=['zero','supervised','team','counterfactual'];group=[raw_metrics[f'{a}-{seed}']['run2']['per_graph'] for a in train_arms]
            jointly_ready=np.array([all(x['nonempty'] and x['parent_ready'] for x in records) for records in zip(*group)])
            for a,records in zip(train_arms,group):
                label=f'{a}-{seed}';counts=dict(graphs=int(jointly_ready.sum()),complete=sum(int(yes and x['complete']) for x,yes in zip(records,jointly_ready)))
                common[tid][label]=counts
                if 'all_arms_ready' in result['panels'][tid][label]:assert counts==result['panels'][tid][label]['all_arms_ready']
            for label,base_values in result['paired'][tid].items():
                if not label.endswith(str(seed)):continue
                comparisons[tid][label]={}
                for ref,old in base_values.items():
                    ref_label=ref if ref.endswith(str(seed)) else f'{ref}-{seed}'
                    calculated=paired_layouts(raw_metrics[ref_label],raw_metrics[label])
                    if calculated!=old:raise ValueError(f'paired mismatch: {tid}/{label}/{ref}')
                    comparisons[tid][label][ref]=calculated
        retention[tid]={}
        for name,recorded in result.get('one_row_retention',{}).get(tid,{}).items():
            trace=root/'retention-traces'/f'{tid}-{name}.npz'
            retention_hashes[trace.name]=file_hash(trace)
            if retention_hashes[trace.name]!=result['retention_sha256'][trace.name]:raise ValueError('retention trace hash mismatch')
            stats=load_trace(trace,data,1)
            for tag,sk in [('run1','r1'),('run2','r2')]:
                for key,value in recorded[sk].items():
                    if isinstance(value,(int,bool)) and stats[tag][key]!=value:raise ValueError(f'{tid}/{name}/retention/{tag}/{key}')
            frozen='frozen1-'+name.rsplit('-',1)[1]
            paired=paired_layouts(raw_metrics[frozen],stats);assert paired==recorded['paired_to_frozen']
            retention[tid][name]=dict(nonempty_complete=stats['run2']['nonempty_complete_graphs'],
                missing=stats['run2']['missing'],duplicates=stats['run2']['duplicates'],wrong_parent=stats['run2']['wrong_parent'],
                paired_nonempty=paired['nonempty'],common_ready=paired['common_parent_ready_nonempty'])
    if set(hashes)!={p.name for p in (root/'traces').glob('*.npz')}:raise ValueError('unexpected trace set')
    if set(retention_hashes)!={p.name for p in (root/'retention-traces').glob('*.npz')}:raise ValueError('unexpected retention trace set')
    assert len(hashes)==30 and len(retention_hashes)==18
    return dict(scope='CPU-only replay of final greedy traces plus original first/last sampled RL training trajectories',
                results_sha256=file_hash(path),trace_sha256=hashes,panels=panels,paired=comparisons,common_ready=common,
                retention_sha256=retention_hashes,one_row_retention=retention,sampled_rewards=sampled_rewards(root))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=replay(args.root);report['source_sha256']=file_hash(Path(__file__))
    if 'torch' in sys.modules or 'mlx.core' in sys.modules:raise RuntimeError('CPU replay loaded a neural backend')
    out=args.output or args.root/'cpu-replay.json';tmp=out.with_suffix('.tmp')
    tmp.write_text(json.dumps(report,separators=(',',':'))+'\n');tmp.replace(out)
    print('replayed',len(report['trace_sha256']),'greedy traces, independently checked complete witnesses, reward, and common ready cases')

if __name__=='__main__':main()
