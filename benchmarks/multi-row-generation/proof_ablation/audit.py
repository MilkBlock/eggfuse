"""Independently replay emitted bindings and effective writes with Rust-derived port partitions."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
from bake import bake,plans,prove

HERE=Path(__file__).resolve().parent
CORPUS=HERE.parent/'eclass_ablation'
sys.path.insert(0,str(CORPUS))
from data import dataset
from data.runtime import partition_record


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(z,d,p,lib,macro):
    mode='macro' if macro else 'primitive'
    wire=z[mode+'_wire'];ranges=z[mode+'_ranges'];verdict=z[mode+'_verdict'];rows=z[mode+'_rows']
    result=Counter();lengths=Counter()
    for g in range(len(d['a'])):
        a,b,req=(d[k][g] for k in ('a','b','requests'))
        ap,phase,committed,ext=(d[k][g] for k in ('a_port','phase','committed','external'))
        groups,_,_=partition_record(d['template'],a,ap,phase,committed,ext)
        legal=[tuple(r[2:4]) in groups[tuple(r[:2])] for r in req]
        expected=np.full_like(rows[g],-1)
        result.update(graphs=1,obligations=sum(legal),active_proposals=int(z['claims'][g,:,0].sum()))
        end=0
        for j,(live,pi,ri,*output) in enumerate(z['claims'][g]):
            off,size=ranges[g,j];assert off==end;end+=size
            yes,work=verdict[g,j]
            if not live:
                assert size==0 and yes==work==0
                continue
            header=wire[g,off:off+6];length=int(header[5])
            assert size==6+length and header[1:5].tolist()==[2,g,pi,ri]
            result.update(packet_bytes=int(size*4),proof_bytes=4*length,steps=int(work),transmitted=1)
            parent,ai,bi,*payload=z['parents'][g,pi];parent_row=payload[:5];q=req[ri]
            valid=(bool(parent) and a[ai,0]==b[bi,0] and list(a[ai,:2])==list(q[2:4]) and legal[ri]
                   and parent_row==[*a[ai],b[bi,1]] and output==[*a[ai,:2],q[4],a[ai,3],b[bi,1]])
            assert yes==valid,(g,j,yes,valid)
            if length:
                program=wire[g,off+6:off+size].tolist()
                if macro:
                    assert length==1
                    x,y,mask,edge,start,count=lib['macros'][program[0]]
                    program=lib['code'][start:start+count]
                x,y,mask,edge=prove(p,program)
                cur,event=z['ctx'][g];read,src=z['requests'][g,ri,-2:]
                assert (x,y)==(lib['public'][read],lib['public'][src]) and (cur&mask)==mask and edge in (0,event)
            if yes:
                result['accepted']+=1
                lengths[len(program)]+=1
                if expected[ri,0]<0:expected[ri]=[pi,ri,*output]
                else:result['duplicates']+=1
        np.testing.assert_array_equal(rows[g],expected)
        published=expected[:,0]>=0
        result.update(unique_writes=int(published.sum()),missing=int(np.sum(legal)-published.sum()),
                      complete=int(np.array_equal(published,legal)))
    return result,lengths


def main(root,producers,out):
    inputs=plans()
    templates=json.loads((CORPUS/'corpus/manifest.json').read_text())['templates']
    measurement=json.loads((root/'measure.json').read_text())
    faults={};scope={};cost={};hashes={};counts={};hist={}
    for name,errors in measurement['faults'].items():
        mode=name.rsplit('/',1)[1]
        for reason,(tested,bad) in errors.items():
            assert tested>0 and bad==0
            faults.setdefault(mode,Counter())[reason]+=tested
    scoped=json.loads((root/'scope-tests.json').read_text())
    for name,results in scoped.items():
        for k,metrics in results.items():scope.setdefault(k,Counter()).update(metrics)
    for t in templates:
        name=t['id'];held=t['split']=='heldout'
        if not held and name not in ('rule-266','rule-267','rule-580'):continue
        split='heldout' if held else 'secondary'
        d=dataset('test',t);p=inputs[name];lib=bake(p)
        samples=[];admission=[]
        for _ in range(12):
            begin=perf_counter_ns();bake(p);samples.append((perf_counter_ns()-begin)/1e6)
            begin=perf_counter_ns()
            for a,b,m,e,start,n in lib['macros']:
                assert prove(p,lib['code'][start:start+n])==(a,b,m,e)
            admission.append((perf_counter_ns()-begin)/1e6)
        cost[name]=dict(macros=len(lib['macros']),instructions=len(lib['code']),longest=max(v[-1] for v in lib['macros']),
                        bake_ms=median(samples),admit_ms=median(admission),device_bytes=measurement['device_bytes'][name])
        for seed in (1703,1709):
            for source in ('neural','all_requests'):
                f=root/'traces'/f'{name}-{seed}-{source}.npz';hashes[f.name]=digest(f)
                with np.load(f,allow_pickle=False) as saved:z=dict(saved)
                for k in ('a','b','requests'):
                    np.testing.assert_array_equal(z[k][...,:d[k].shape[-1]],d[k])
                if source=='neural' and held:
                    with np.load(producers/'traces'/f'{name}-pairwise-{seed}.npz') as old:
                        for new,orig in [('parents','0'),('claims','1')]:
                            for key,selection in [('active',0),('pointers',slice(1,3)),('rows',slice(3,8))]:
                                np.testing.assert_array_equal(z[new][...,selection],old[f'{orig}_{key}'])
                for macro in (False,True):
                    mode='macro' if macro else 'primitive';key=f'{split}/{seed}/{source}/{mode}'
                    result,lengths=check(z,d,p,lib,macro)
                    if source=='all_requests' and result['missing']:raise ValueError((name,result))
                    counts.setdefault(key,Counter()).update(result);hist.setdefault(key,Counter()).update(lengths)
    assert len(hashes)==24 and set(hashes)=={p.name for p in (root/'traces').glob('*.npz')}
    if 'torch' in sys.modules:raise RuntimeError('auditor imported PyTorch')
    out.mkdir(parents=True,exist_ok=True)
    fields=sorted(set().union(*(v.keys() for v in counts.values())))
    with (out/'metrics.tsv').open('w') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n')
        w.writerow(['panel','seed','source','verifier',*fields])
        for key,v in counts.items():w.writerow([*key.split('/'),*(v[k] for k in fields)])
    (out/'summary.json').write_text(json.dumps(dict(cost=cost,accepted_proof_lengths=hist,rejected_faults=faults,
        scope_challenges=scope,median_ms=measurement['median_ms'],trace_hashes=hashes,
        measurement_sha256=digest(root/'measure.json'),scope_sha256=digest(root/'scope-tests.json')),indent=1)+'\n')
    print('Replayed 24 GPU traces; verified proposal decisions and publication order.')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','producers','out'):p.add_argument(name,type=Path)
    a=p.parse_args();main(a.root,a.producers,a.out)
