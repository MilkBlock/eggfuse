"""Independent replay of arena lifetimes, visible fields, Rust-backed port truth and parent identity."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'union_ablation'))
from audit_union import truth,CORPUS,dataset,digest

MODES=('source','primary','integral','learned_integral','unchecked','early_public','stable_integral')
DUE=(0,1,1,2)


def replay(z,ref,d,baseline,mode):
    # Identical A-visible inputs must yield the same private state even if a
    # later local commit or external edge differs.
    variants={}
    prefix_fields=('a','b','requests','a_port','request_ports')
    for i in range(len(d['a'])):
        key=tuple(d[k][i].tobytes() for k in prefix_fields)
        variants.setdefault(key,[]).append(i)
    distinct_futures=0
    for ids in variants.values():
        if len({(d['committed'][i].tobytes(),d['external'][i].tobytes()) for i in ids})<2:
            continue
        distinct_futures+=1
        for k in ('admission','0_ref','0_pool','0_stats','0_pub'):
            assert (z[k][ids]==z[k][ids[0]]).all(),(mode,k,'future-dependent A state')
    assert distinct_futures>0
    ok_all=np.ones(len(d['a']),bool)
    batch=len(ok_all);graphs=np.arange(batch)[:,None]
    first={k:z['first_'+k] for k in ('pointers','active','rows')}
    for key,a in first.items():np.testing.assert_array_equal(a,baseline['first_'+key])
    # Resolve only from the actual producer's ordered input witnesses and the
    # original Request's identity, independently of GPU member construction.
    ptr=baseline['0_pointers'][...,0]
    ai,bi=first['pointers'][graphs,ptr].transpose(2,0,1)
    a=d['a'][graphs,ai];b=d['b'][graphs,bi];req=d['requests']
    ready=(first['active'][graphs,ptr]>0)&(a[...,0]==b[...,0])&(a[...,:2]==req[...,2:4]).all(-1)
    projected=np.stack((a[...,0],a[...,1],req[...,4],a[...,3],b[...,1]),-1)
    counts=Counter(graphs=batch,matched_future_groups=distinct_futures);prev=None;curve=[]
    birth_serials={};prev_visible=None
    for stage,tick in enumerate((0,2,3)):
        h,pool,log,obs,pub=[z[f'{stage}_{k}'] for k in ('ref','pool','stats','obs','pub')]
        accepted=obs[:,6:].astype(bool)
        np.testing.assert_array_equal(accepted,ref[stage][1])
        labels=obs[:,:6];np.testing.assert_array_equal(labels[:,:,None]==labels[:,None,:],ref[stage][0])
        np.testing.assert_array_equal(log[:,22],0)
        occupied=pool[:,:,0]>=0
        np.testing.assert_array_equal(occupied.sum(1),log[:,0])
        np.testing.assert_array_equal(log[:,0],(h>=0).sum(1))
        for graph in range(batch):
            named=h[graph,h[graph]>=0]
            assert len(set(named))==len(named) and occupied[graph,named].all()
        result_ok=np.ones(batch,bool)
        priv=0;premature=0;published_early=0
        fields=pub.reshape(batch,4,4,14);released=fields[...,0]>=0
        visible=np.zeros_like(released)
        for op,due in enumerate(DUE):
            slots=h[:,op::4];exists=slots>=0;r=pool[graphs,slots.clip(0)]
            assert (r[...,1][exists]==np.broadcast_to(np.arange(4),exists.shape)[exists]).all()
            assert (r[...,2][exists]==op).all()
            if op:
                parent=pool[graphs,h[:,op-1::4].clip(0)]
                assert ((h[:,op-1::4]>=0)&(r[...,5]==parent[...,0]))[exists].all()
            visible[...,op]=ready & (due<=stage)
            actual=released[...,op]
            # Verify what the public reader really received from the arena port.
            np.testing.assert_array_equal(fields[:,:,op][actual],r[actual])
            expected_fields=projected if op>=2 else first['rows'][graphs,ptr]
            valid_fields=(r[...,9:14]==expected_fields).all(-1)&(r[...,6]==ptr)
            if op>=1:valid_fields &= r[...,7]==ref[1][1]
            if op==3:valid_fields &= r[...,8]==ref[2][1]
            result_ok &= ((actual==visible[...,op])&(~actual|valid_fields)).all(1)
            premature+=int((actual & (due>stage)).sum());priv+=int((exists&~actual).sum())
            if stage and due==stage:
                oldslot,oldgen=birth_serials[op]
                reused=exists & (r[...,3]<stage)
                if reused.any():
                    assert np.array_equal(slots[reused],oldslot[reused]) and np.array_equal(r[...,0][reused],oldgen[reused])
                published_early+=int((actual&reused).sum())
            birth_serials[op]=slots.copy(),np.where(exists,r[...,0],-1)
        if prev_visible is None:prev_visible=np.zeros_like(released)
        # Original writes are stable observations even when a subsequent union changes a comparison.
        if prev is not None:
            stability=(fields==prev).all(-1)
            result_ok &= (~prev_visible|stability).all((1,2))
        delta=released&~prev_visible
        expected_delta=np.stack([ready & (due==stage) for due in DUE],-1)
        result_ok &= (delta==expected_delta).all((1,2))
        prev,prev_visible=fields.copy(),released.copy()
        ok_all &= result_ok
        counts[f'correct_{stage}']=int(result_ok.sum())
        counts[f'live_{stage}']=int(log[:,0].sum());counts[f'private_{stage}']=priv
        counts[f'allocations_{stage}']=int(log[:,2].sum())
        counts[f'premature_{stage}']=premature
        counts[f'promotions_{stage}']=published_early
        curve.append(published_early)
    for op in range(4):
        for k,col in [('alloc',4),('invalid',8),('reuse',12),('early',16)]:
            counts[f'{k}_{op}']=int(log[:,col+op].sum())
    counts['all_exact']=int(ok_all.sum())
    counts['sweeps']=int(log[:,3].sum());counts['peak']=int(log[:,1].sum())
    counts['admitted']=int(z['admission'].sum())
    counts['changed_local']=int((ref[0][1]!=ref[1][1]).sum());counts['changed_external']=int((ref[1][1]!=ref[2][1]).sum())
    if mode not in ('unchecked','early_public'):
        assert ok_all.all() and sum(curve)==sum(counts[f'reuse_{k}'] for k in range(4))
        for op in range(4):assert counts[f'early_{op}']==counts[f'invalid_{op}']+counts[f'reuse_{op}']
    return counts


def main(root,prior,out):
    old=json.loads((HERE.parent/'union_ablation/results/summary.json').read_text())['trace_sha256']
    templates=json.loads((CORPUS/'corpus/manifest.json').read_text())['templates']
    panels={};hashes={}
    for t in templates:
        name=t['id'];split='heldout' if t['split']=='heldout' else 'secondary'
        if split=='secondary' and name not in ('rule-266','rule-267','rule-580'):continue
        d=dataset('test',t);ref=[truth(d,tick) for tick in (0,2,3)]
        for seed in (1703,1709):
            path=prior/'traces'/f'{seed}-{name}-each-fenced.npz';assert digest(path)==old[path.name]
            with np.load(path) as fd:base=dict(fd)
            for mode in MODES:
                path=root/'traces'/f'{name}-{seed}-{mode}.npz';hashes[path.name]=digest(path)
                with np.load(path,allow_pickle=False) as fd:r=replay(dict(fd),ref,d,base,mode)
                panels.setdefault(f'{split}/{seed}/{mode}',Counter()).update(r)
    assert set(hashes)=={p.name for p in (root/'traces').glob('*.npz')} and len(hashes)==84
    if 'torch' in sys.modules:raise RuntimeError('host audit imported PyTorch')
    out.mkdir(parents=True,exist_ok=True);fields=list(next(iter(panels.values())))
    with (out/'metrics.tsv').open('w') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n');w.writerow(['panel','seed','mode',*fields])
        for name,counts in panels.items():w.writerow([*name.split('/'),*(counts[k] for k in fields)])
    timing=json.loads((root/'timing.json').read_text())
    (out/'summary.json').write_text(json.dumps(dict(traces=hashes,timing_sha256=digest(root/'timing.json'),
        median_ms=timing['medians']),indent=1)+'\n')
    print('Checked 84 actual GPU trajectories and all three public views')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('root','prior','out'):p.add_argument(key,type=Path)
    a=p.parse_args();main(a.root,a.prior,a.out)
