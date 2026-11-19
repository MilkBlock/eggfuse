"""Read only saved device outputs. Check source semantics, claims, maps and old cursors."""
import argparse
from collections import Counter
import csv
import hashlib
from itertools import combinations,product
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'eclass_ablation'))
from data import dataset

PAIRS=np.array(list(combinations(range(8),2)))
ASSIGN=np.array([(i,j) for i,j in product(range(28),repeat=2) if not set(PAIRS[i])&set(PAIRS[j])])
MODES=('retain','forward','no_retry','blind','unguarded','forward_joint','exact_joint')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(z,base,d,mode,at,collision):
    token=z['token']; n=len(token);g=np.arange(n)
    scores=z['scores'];log=z['log'];targets=z['targets'];h=z['headers']
    for k in ('active','pointers','rows'):np.testing.assert_array_equal(z['first_'+k],base['first_'+k])
    rows=base['first_rows']
    np.testing.assert_array_equal(token[...,50:55],rows)
    np.testing.assert_array_equal(token[...,32:34].argmax(-1),base['first_active'])
    for start,j in [(34,0),(42,1)]:
        np.testing.assert_array_equal(token[...,start:start+8].argmax(-1),base['first_pointers'][...,j])
    valid=base['first_active'].astype(bool)
    b=base['first_pointers'][...,1]
    free=np.ones((n,8),bool)
    selected=np.full((n,2,2),-1,int)
    accepted=np.zeros((n,2),bool)
    conflicts=np.zeros((n,2),bool)
    multi=np.zeros(n,bool)
    req=d['requests'][...,2:4].reshape(n,2,2,2).transpose(0,2,1,3)
    if collision:req=np.repeat(req[:,:1],2,axis=1)
    hit=(rows[:,None,:,None,:2]==req[:,:,None,:,:]).all(-1)
    l,r=PAIRS.T
    paired=valid[:,l]&valid[:,r]&(b[:,l]==b[:,r])
    utility=(hit[:,:,l]|hit[:,:,r]).sum(-1)
    exact=np.where(paired[:,None],1+utility,-3)
    if mode=='exact_joint':np.testing.assert_array_equal(scores,exact)
    result=Counter(graphs=n)
    score_of_commits=np.zeros(n,int)
    joint=mode in ('exact_joint','forward_joint')
    for round_id in range(1 if mode=='no_retry' or joint else 2):
        available=free[:,l]&free[:,r]
        if joint:
            choice=(scores[:,0,ASSIGN[:,0]]+scores[:,1,ASSIGN[:,1]]).argmax(-1)
            actions=ASSIGN[choice]
        else:
            actions=np.where(available[:,None],scores,-np.inf).argmax(-1)
        for row in (0,1):
            pair=PAIRS[actions[:,row]];left,right=pair.T
            np.testing.assert_array_equal(log[:,round_id,row,:2],pair)
            try_it=conflicts[:,row] if round_id else np.ones(n,bool)
            taken=~(free[g,left]&free[g,right])
            eligible=paired[g,actions[:,row]]
            code=np.where(~try_it,0,np.where(taken & (mode!='unguarded'),2,np.where(eligible,1,3)))
            np.testing.assert_array_equal(log[:,round_id,row,2],code)
            win=code==1; multi |= win&taken
            if round_id==0:conflicts[:,row]=code==2
            result['first_conflicts' if round_id==0 else 'retry_conflicts']+=int((code==2).sum())
            result['first_accept' if round_id==0 else 'retry_accept']+=int(win.sum())
            result['invalid_proposals']+=int((code==3).sum())
            selected[win,row]=pair[win];accepted[:,row]|=win
            free[g[win],left[win]]=False;free[g[win],right[win]]=False
            score_of_commits+=win*utility[g,row,actions[:,row]]
    np.testing.assert_array_equal(targets[...,0],accepted)
    for row in (0,1):
        win=accepted[:,row];ids=g[win];ix=selected[win,row]
        np.testing.assert_array_equal(targets[win,row,1:],ix)
        left=token[ids,ix[:,0]];right=token[ids,ix[:,1]]
        np.testing.assert_array_equal(z['boundary'][win,row],np.concatenate([left[:,50:55],right[:,51:54]],-1))
        for side,v in enumerate((left,right)):
            np.testing.assert_array_equal(z['residual'][win,row,side],np.concatenate((v[:,:50],v[:,55:]),-1))
    both_legal=paired[:,ASSIGN[:,0]]&paired[:,ASSIGN[:,1]]
    best=np.where(both_legal,utility[:,0,ASSIGN[:,0]]+utility[:,1,ASSIGN[:,1]],-1).max(1)
    result.update(double_claim_graphs=int(multi.sum()),two_compositions=int(accepted.all(-1).sum()),
                  moved_instances=int((~free).sum()),assigned_reads=int(score_of_commits.sum()),
                  max_disjoint_reads=int(best.sum()),at_max_disjoint=int(((score_of_commits==best)&~multi).sum()))
    # A correct result cannot bypass a poisoned generation by using a cached answer.
    retired=~free if mode not in ('retain','unguarded') else np.zeros_like(free)
    source=z['physical'];fresh=z['fresh_state']
    np.testing.assert_array_equal(h[...,0],1+retired.astype(int))
    np.testing.assert_array_equal(source[~retired],token[~retired])
    if retired.any():assert (source[retired]<0).all()
    if mode!='blind':
        np.testing.assert_array_equal(fresh,retired.astype(int))
        np.testing.assert_array_equal(z['fresh'][retired],source[retired])
        assert not z['unknown'].any()
        np.testing.assert_array_equal(z['old_state'],1+retired.astype(int))
        np.testing.assert_array_equal(z['old'].view('uint32'),token.view('uint32'))
    old_ok=(z['old'].view('uint32')==token.view('uint32')).all((1,2))
    result['old_tokens_bitwise_exact']=int(old_ok.sum())
    result['unknown_generations_accepted']=int((z['unknown']>0).sum())
    ok=np.ones(n,bool)
    waiting=None
    for tick in range(4):
        active=base[f'{tick}_active'].astype(bool)
        for field in ('classes','legality','delta','published','active','published_refs','published_rows'):
            equal=(z[f'{tick}_{field}']==base[f'{tick}_{field}']).reshape(n,-1).all(-1)
            ok &= equal
        rhs=(z[f'{tick}_rows']==base[f'{tick}_rows']).all(-1)
        witness=(z[f'{tick}_pointers']==base[f'{tick}_pointers']).all(-1)
        ok &= (~active|(rhs&witness)).all(1)
        ptr=base[f'{tick}_pointers'][...,0];through=(z['cursors'][:,tick]==2)
        expected=(retired[g[:,None],ptr] if tick>=at and mode!='blind' else np.zeros_like(active))
        np.testing.assert_array_equal(through,expected)
        result['forwarded_live_reads']+=int((through&active).sum())
        if tick==2:waiting=~active
        if tick==3:
            awakened=waiting&active
            result['externally_awakened']+=int(awakened.sum())
            result['awakened_via_forward']+=int((awakened&through&rhs&witness).sum())
            result['wrong_final_graphs']=int((~(z['3_published_rows']==base['3_published_rows']).all((1,2))).sum())
    result['all_runs_exact']=int(ok.sum())
    result['storage_and_runs_exact']=int((ok&old_ok&~multi&~(z['unknown']>0).any(1)).sum())
    if mode not in ('blind','unguarded') and result['storage_and_runs_exact']!=n:
        raise ValueError((mode,at,result))
    return result


def replay(root,union_root,out):
    manifest=json.loads((HERE.parent/'eclass_ablation/corpus/manifest.json').read_text())
    refs=json.loads((HERE.parent/'union_ablation/results/summary.json').read_text())['trace_sha256']
    snapshots={};stats={};frozen={}
    for t in manifest['templates']:
        split='heldout' if t['split']=='heldout' else 'secondary'
        name=t['id']
        if split=='secondary' and name not in ('rule-266','rule-267','rule-580'):continue
        d=dataset('test',t)
        for seed in (1703,1709):
            f=union_root/'traces'/f'{seed}-{name}-each-fenced.npz'
            frozen[f.name]=digest(f)
            assert frozen[f.name]==refs[f.name]
            with np.load(f,allow_pickle=False) as zz:base=dict(zz)
            for collision in (0,1):
                for at in (1,3):
                    matched={}
                    for mode in MODES:
                        p=root/'traces'/f'{seed}-{name}-{collision}-{at}-{mode}.npz'
                        snapshots[p.name]=digest(p)
                        with np.load(p,allow_pickle=False) as archive:z=dict(archive)
                        if mode=='retain':
                            matched={k:z[k] for k in ('scores','log','targets','old')}
                        if mode=='forward':
                            for k,v in matched.items():np.testing.assert_array_equal(z[k],v)
                        report=check(z,base,d,mode,at,collision)
                        stats.setdefault(f'{seed}/{split}/{collision}/{at}/{mode}',Counter()).update(report)
    if set(snapshots)!={p.name for p in (root/'traces').glob('*.npz')}:raise ValueError('trajectory set changed')
    if 'torch' in sys.modules:raise RuntimeError('CPU audit imported neural runtime')
    out.mkdir(exist_ok=True)
    keys=sorted(set().union(*(r.keys() for r in stats.values())))
    with (out/'metrics.tsv').open('w') as h:
        w=csv.writer(h,delimiter='\t',lineterminator='\n')
        w.writerow(['seed','panel','same_requests','transition_tick','mode',*keys])
        for k,r in stats.items():w.writerow([*k.split('/'),*(r[field] for field in keys)])
    time=json.loads((root/'timing.json').read_text());time.pop('samples_ms')
    (out/'summary.json').write_text(json.dumps(dict(trace_count=len(snapshots),trace_hashes=snapshots,
        reference_hashes=frozen,timing=time,timing_sha256=digest(root/'timing.json'),
        weights={s:json.loads((root/f'actor-{s}.json').read_text()) for s in (1703,1709)}),indent=1)+'\n')
    print('CPU replay verified',len(snapshots),'GPU traces and 12 frozen source panels')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','union_root','out'):p.add_argument(name,type=Path)
    a=p.parse_args();replay(a.root,a.union_root,a.out)
