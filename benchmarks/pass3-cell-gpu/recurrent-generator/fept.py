"""Attribute retained physical constructor rows to committed explicit token proposals."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess

import numpy as np
import torch
from capture import execute, inputs, read, verify
from chain_check import serial_compiler


def retained(source,image):
    spans=np.load(source/'birth-ranges.npy',allow_pickle=False)
    with np.load(source/'output.npz') as g:
        rows=g['meta']
        epochs=g['birth_runs']
        runs=g['rhs'][:,0]
    begin,end=spans.T
    assert len(begin)==len(runs) and np.all(begin<=end) and np.all(end[:-1]<=begin[1:])
    assert begin.min()>=0 and end.max()<=len(rows)
    rhs_owner=np.zeros(len(rows),dtype=np.int32)
    for i,(first,stop) in enumerate(spans,1):
        rhs_owner[first:stop]=i
    np.testing.assert_array_equal(rhs_owner>0,epochs>0)
    np.testing.assert_array_equal(epochs[rhs_owner>0],runs[rhs_owner[rhs_owner>0]-1])
    kinds=np.array([t['kind']=='constructor' for t in read(image/'ingress.json')['tables']])
    counted=(rhs_owner>0) & kinds[rows[:,0]] & (rows[:,3]==0)
    return np.bincount(rhs_owner[counted],minlength=len(runs)+1)


def winning_proposals(dest):
    with np.load(dest/'neural-output.npz') as n,np.load(dest/'compound-output.npz') as c:
        raw=n['raw']
        root=n['rhs_ordinal'][:,:2]
        assert not np.any((root>0)&(raw[:,:2,11]==0))
        ordinals=[root[root>0]]
        for key in ('claims','tails',*[k for k in c if k.startswith('hop_')]):
            won=c[key][:,:,7]
            assert not np.any((won>0)&(raw[:,2:,11]==0))
            ordinals.append(won[won>0])
        paid=int(np.count_nonzero(raw[:,:,11]))
    ordinals=np.concatenate(ordinals)
    if len(np.unique(ordinals))!=len(ordinals):raise ValueError('duplicate committed ordinal')
    return ordinals,paid


def measure(dest,source,counts):
    # Accepted source equality precedes the transfer of any per-ordinal credit.
    np.testing.assert_array_equal(np.load(dest/'birth-ranges.npy'),np.load(source/'birth-ranges.npy'))
    with np.load(dest/'output.npz') as actual,np.load(source/'output.npz') as baseline:
        for key in ('meta','birth_runs'):
            np.testing.assert_array_equal(actual[key],baseline[key])
        np.testing.assert_array_equal(actual['rhs'][:,:2],baseline['rhs'][:,:2])
        np.testing.assert_array_equal(actual['rhs'][:,4:],baseline['rhs'][:,4:])
    ordinals,paid = winning_proposals(dest)
    numerator=int(counts[ordinals].sum())
    cross={}
    if (source/'rust-visible-by-rhs.npy').exists():
        rust=np.load(source/'rust-visible-by-rhs.npy')
        cross=dict(rust_visible=int(rust[ordinals].sum()),disputed_winners=int((rust[ordinals]!=counts[ordinals]).sum()))
    return dict(**cross,visible=numerator,issued=paid,fept=numerator/paid if paid else None,
                source_visible=int(counts.sum()),commits=len(ordinals))


def verify_native(binary,program,source,counts):
    """Rebuild the numerator using Rust FactRefs, endpoint visibility and RHS locations."""
    request=json.dumps(dict(baseline=True,birth_ledger=True,audit=True))+"\n"
    result=subprocess.run([binary,program,'/dev/null'],input=request,text=True,
                          capture_output=True,check=True)
    native=json.loads(result.stdout)
    with np.load(source/'output.npz') as g:
        runs=g['runs']
        rhs=g['rhs']
    ledger=native['constructor_births']
    if len(native['events'])!=len(runs):
        raise ValueError("native source schedule differs")
    visible={fact for fact,t,hidden in ledger['endpoint'] if not hidden and native['constructor_schema'][t]}
    offsets=np.cumsum(runs[:,1])-runs[:,1]
    per_rhs=np.zeros_like(counts)
    seen=set()
    for i,events in enumerate(native['events']):
        for event in events:
            if event[0]!='birth' or event[4] not in visible or event[5] is None:continue
            fact=event[4]
            pos,rid=event[5][:2]
            assert fact not in seen and 0<=pos<runs[i,1]
            seen.add(fact)
            j=int(offsets[i]+pos)
            assert rhs[j,0]==i+1 and rhs[j,1]==rid
            per_rhs[j+1]+=1
    # Original witness retention may differ across backends after a collision.
    # Preserve the disagreement; never silently transfer credit at those ordinals.
    np.save(source/'rust-visible-by-rhs.npy',per_rhs)
    diff=np.flatnonzero(per_rhs!=counts)
    (source/'rust-retention.json').write_text(json.dumps(dict(native=int(per_rhs.sum()),
        kernel=int(counts.sum()),differences=[[int(i),int(per_rhs[i]),int(counts[i])] for i in diff]),indent=2)+'\n')


def main(a):
    torch.set_num_threads(1)
    ref=a.exp/'pass3-release-reproduction-20261120'
    for case in a.cases:
        image,program,gold=inputs(a.exp/'repair-bake-families-20261120',ref,case)
        dest=a.out/case
        if not a.check_existing:
            with TemporaryDirectory() as tmp:
                execute(image/'device.json',a.exp/'rotary-axes-20261119/packed-1703/final.pt',
                    ref/'ports-1703.pt',2048,2,dest,birth_audit=True,serial_compile=serial_compiler(Path(tmp)))
        verify(dest,gold,image)
        counts=retained(dest,image)
        if a.native:verify_native(a.native,program,dest,counts)
        print(case,len(counts)-1,int(counts.sum()),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exp',type=Path);p.add_argument('out',type=Path);p.add_argument('cases',nargs='+')
    p.add_argument('--native',type=Path)
    p.add_argument('--check-existing',action='store_true')
    main(p.parse_args())
