"""CPU-only validation of saved gate decisions, scorer counters and training interventions."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

from audit_gate import execution_metrics,gate_bits,metrics,paired_readiness,timed_rates,verify_token
from gate_data import BASE,array_digest,dataset,fresh_panel,templates
sys.path.append(str(BASE))
from credit_ablation.replay import numpy_reward

KEYS=('active','pointers','rows','gate_open')


def file_hash(path):return sha256(path.read_bytes()).hexdigest()


def subset(d,ix):return {k:(v[ix] if isinstance(v,np.ndarray) else v) for k,v in d.items()}


def trace(z,prefix=''):
    out=[]
    for i in (0,1):
        stage={k:z[f'{prefix}{i}_{k}'] for k in KEYS}
        for key in ('executed','work_checksum'):
            if f'{prefix}{i}_{key}' in z:stage[key]=z[f'{prefix}{i}_{key}']
        out.append(stage)
    return out,z[prefix+'token']


def validate_branch_pair(opened,closed,open_token,closed_token,sites):
    """One gate is forcibly changed; compare the actual common execution prefix.

    Physical site numbering is Run-major and then row-major (row*4 + time).
    A sibling lane in the same Run has unchanged source inputs and depends only
    on its own preceding token. Both stage decisions and the producer state are
    checked under this conditional intervention.
    """
    if sites.dtype.kind not in 'iu' or sites.ndim!=1 or (sites<0).any() or (sites>=16).any():
        raise ValueError('invalid counterfactual intervention sites')
    slots=np.arange(8);physical_row=slots//4;round_number=slots%4
    for g,site in enumerate(sites):
        forced_run,slot=divmod(int(site),8);row,t=divmod(slot,4)
        if opened[forced_run]['gate_open'][g,slot]!=1 or closed[forced_run]['gate_open'][g,slot]!=0:
            raise ValueError('site was not forced open/closed as declared')
        for i,(one,two) in enumerate(zip(opened,closed)):
            if i>forced_run:continue
            equal=np.ones(8,bool) if i<forced_run else ((round_number<t)|(physical_row!=row))
            for key in KEYS:np.testing.assert_array_equal(one[key][g,equal],two[key][g,equal])
            if i==0:np.testing.assert_array_equal(open_token[g,equal],closed_token[g,equal])


def training_replay(root):
    ts={t['id']:t for t in templates() if t['split']=='train'};panels={};samples={}
    for seed in (1703,1709):
        for price in (0.,.25):
            name=f'gate_p{int(100*price)}-{seed}';folder=root/name;items={}
            for step in (1,1024):
                path=folder/f'sampled-{step}.npz'
                with np.load(path,allow_pickle=False) as z:
                    tid=str(z['template'].item());indices=z['indices'];sites=z['sites'];
                    if tid not in ts:raise ValueError('sample uses held-out source template')
                    if tid not in panels:panels[tid]=dataset('train',ts[tid])
                    if indices.dtype.kind not in 'iu' or indices.shape!=(32,) or (indices<0).any() or (indices>=len(panels[tid]['a'])).any():
                        raise ValueError('invalid saved training indices')
                    d=subset(panels[tid],indices);observed_price=float(z['price'].item())
                    if not np.isclose(observed_price,price):raise ValueError('saved price differs from training arm')
                    branches={};states={};utilities={}
                    for side in ('open','closed'):
                        prefix=side+'_';stage,token=trace(z,prefix);states[side]=(stage,token)
                        bits=gate_bits(None,*stage);verify_token(d,*stage,token,bits)
                        # Recompute only from source facts, certified equalities and emitted addresses.
                        report=metrics(d,*stage,bits);reward,_=numpy_reward(d,*stage,report)
                        cost=bits.sum(axis=(1,2,3))/16;utility=reward-price*cost
                        for key,expected in [('reward',reward),('utility',utility)]:
                            np.testing.assert_allclose(z[prefix+key],expected,rtol=0,atol=2e-7,err_msg=f'{name}/{step}/{side}/{key}')
                        utilities[side]=utility
                        branches[side]=dict(open_slots_per_graph=(cost*16).astype(int).tolist(),reward_by_graph=reward.tolist(),
                            utility_by_graph=utility.tolist(),max_reward_error=float(np.abs(z[prefix+'reward']-reward).max()),
                            max_utility_error=float(np.abs(z[prefix+'utility']-utility).max()),
                            nonempty_complete=report['run2']['nonempty_complete_graphs'],missing=report['run2']['missing'])
                    validate_branch_pair(states['open'][0],states['closed'][0],states['open'][1],states['closed'][1],sites)
                    delta=utilities['open']-utilities['closed']
                    np.testing.assert_allclose(z['delta'],delta,rtol=0,atol=3e-7)
                    items[str(step)]=dict(graphs=len(indices),template=tid,trace_sha256=file_hash(path),
                        source_sha256=array_digest(d),matched_prefix_and_unaffected_lane=True,
                        max_delta_error=float(np.abs(z['delta']-delta).max()),delta_by_graph=delta.tolist(),branches=branches)
            samples[name]=items
    return samples


def compact_per_graph(items):
    result={k:[g[k] for g in items] for k in items[0] if k!='per_round'}
    result['per_round']={k:[[e[k] for e in g['per_round']] for g in items]
                         for k in items[0]['per_round'][0] if k!='round'}
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();root=args.root;report_path=root/'results.json';source=json.loads(report_path.read_text());frozen=json.loads((root/'fresh-gate-inputs.json').read_text())
    out={};hashes={};timing_replay={};held=[t for t in templates() if t['split']=='heldout']
    if {t['id'] for t in held}!=set(source['panels']):raise ValueError('expected all held-out templates')
    for t in held:
        tid=t['id'];d=fresh_panel(t);out[tid]={};timing_replay[tid]={}
        if array_digest(d)!=frozen['panels'][tid]['digest']:raise ValueError(f'{tid}: source input bytes changed')
        for name,stored in source['panels'][tid].items():
            path=root/'traces'/f'{tid}-{name}.npz';hashes[path.name]=file_hash(path)
            if hashes[path.name]!=source['trace_sha256'][path.name]:raise ValueError('trace hash mismatch')
            with np.load(path,allow_pickle=False) as z:
                stages,token=trace(z);rel=z['rel'];bits=gate_bits(None,*stages);verify_token(d,*stages,token,bits)
                if not np.isfinite(rel).all():raise ValueError('nonfinite relation logits')
                # All eight state/required-origin variants share the producer inputs.
                grouped=token.reshape(-1,8,*token.shape[1:]);np.testing.assert_array_equal(grouped,np.broadcast_to(grouped[:,:1],grouped.shape))
                r=metrics(d,*stages,bits,rel);scores,_=numpy_reward(d,*stages,r)
                for sk,key in [('run1','r1'),('run2','r2')]:
                    for k,v in stored[key].items():
                        if isinstance(v,(int,bool)) and r[sk][k]!=v:raise ValueError(f'{tid}/{name}/{sk}/{k}')
                    if 'gate' in stored:
                        for k,v in stored['gate'][sk].items():
                            if r['gate'][sk][k]!=v:raise ValueError(f'{tid}/{name}/gate/{sk}/{k}')
                for k in ('origin_switch','paired_controls'):
                    if k in stored and r[k]!=stored[k]:raise ValueError(f'{tid}/{name}/{k}')
                if stored['complete_by_graph']!=[int(g['complete']) for g in r['run2']['per_graph']]:raise ValueError('whole-graph mismatch')
                if stored['parent_ready']!=[int(g['parent_ready']) for g in r['run2']['per_graph']]:raise ValueError('parent-readiness mismatch')
                execution=None
                if 'executed' in stages[0]:
                    backend=next((k for k in ('metal_skip','metal_dense') if k in name),'dense')
                    execution=execution_metrics(*stages,backend,bits)
                    for sk,(left,right) in zip(('run1','run2'),[(d['a'].shape[1],d['b'].shape[1]),(8,d['requests'].shape[1])]):
                        row=execution[sk];per_scorer=32*(55+2*32+2+left+right)
                        row.update(body_macs_per_executed_row=per_scorer,estimated_body_macs=row['executed_scorer_rows']*per_scorer,
                                   estimated_saved_body_macs=row['skipped_scorer_rows']*per_scorer)
                    if stored.get('execution')!=execution:raise ValueError('recorded work counters differ')
                elif name.find('metal_')>=0:raise ValueError('Metal arm is missing its actual body-entry observations')
                # The timed outputs were audited directly by the evaluator. If
                # their discrete decisions equal the retained full-panel run,
                # recompute every readiness bucket using just these samples.
                timed=source['timings'].get(tid,{}).get(name)
                if timed is not None:
                    differences=timed['bulk_hard_differences'];identical=not any(differences)
                    if identical:
                        selected=[r['gate']['run2']['per_graph'][i] for i in timed['indices']]
                        rates=timed_rates({'gate':{'run2':{'per_graph':selected}}},timed['samples_ms'])
                        if rates!=timed['rates']:raise ValueError(f'{tid}/{name}: timed readiness buckets differ')
                    timing_replay[tid][name]=dict(batch_one_matches_bulk_hard=identical,bulk_hard_differences=differences,
                                                   recomputed_from_retained_trace=identical)
                out[tid][name]=dict(reward_by_graph=scores.tolist(),mean_team_reward=float(scores.mean()),
                     gates={k:compact_per_graph(r['gate'][k]['per_graph']) for k in ('run1','run2')},
                     source_complete=[g['complete'] for g in r['run2']['per_graph']],execution=execution,
                     paired_readiness=paired_readiness(d,r))
    if set(hashes)!={p.name for p in (root/'traces').glob('*.npz')}:raise ValueError('unexpected extra/missing traces')
    result=dict(scope='CPU-only audit of saved globally synchronized outputs, physical scorer observations, and sampled gate interventions',
                traces_sha256=hashes,results_sha256=file_hash(report_path),frozen_inputs_sha256=file_hash(root/'fresh-gate-inputs.json'),
                panels=out,timing_readiness_checks=timing_replay,training=training_replay(root))
    if 'torch' in sys.modules or 'mlx.core' in sys.modules:raise RuntimeError('CPU replay imported neural runtime')
    path=args.output or root/'cpu-replay.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(result,separators=(',',':'))+'\n');tmp.replace(path)
    print('verified',len(hashes),'inference traces and 8 paired sampled training batches')

if __name__=='__main__':main()
