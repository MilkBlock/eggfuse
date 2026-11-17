"""Offline teacher (DSU) and independently implemented post-hoc checker (relations)."""
import sys
from pathlib import Path
import numpy as np
sys.path.append(str(Path(__file__).resolve().parents[1]))
from contract import cpu_unrotate
from spec import SHAPES, UNIONS, MAPS, PAIRS, SPECS, BOOL, OFFSETS, layout_for


def teacher_eq(case,stage):
    shape,ui,_,enabled,_,_,_=map(int,case)
    parent=list(range(8))
    def root(x):
        while parent[x]!=x: x=parent[x]
        return x
    def union(a,b):
        a,b=root(a),root(b)
        if a==b:return False
        parent[max(a,b)]=min(a,b);return True
    if stage>=2 and enabled:union(*UNIONS[ui])
    changed=True
    while changed:
        changed=False;seen={}
        for out,(op,a,b) in enumerate(SHAPES[shape],4):
            key=(op,root(a),root(b) if op else -1)
            if key in seen:changed=union(out,seen[key]) or changed
            else:seen[key]=out
    return np.array([[root(a)==root(b) for b in range(8)] for a in range(8)])


def checker_eq(case,stage):
    """No DSU or teacher call: relational transitivity and pairwise congruence."""
    shape,ui,_,enabled,_,_,_=map(int,case)
    eq=np.eye(8,dtype=bool)
    if stage>=2 and enabled:
        a,b=UNIONS[ui];eq[a,b]=eq[b,a]=True
    while True:
        before=eq.copy()
        for k in range(8):eq |= eq[:,k,None] & eq[None,k,:]
        for i,(op,a,b) in enumerate(SHAPES[shape],4):
            for j,(op2,c,d) in enumerate(SHAPES[shape],4):
                if op==op2 and eq[a,c] and (op==0 or eq[b,d]):eq[i,j]=eq[j,i]=True
        if np.array_equal(before,eq):return eq


def labels(case):
    si,ui,mi,on,q,r,tag=map(int,case); plan=SHAPES[si]; outputs=[]
    for stage in (1,2,3):
        eq=teacher_eq(case,stage); transfer=stage==3 and eq[q,r]
        layout=layout_for(MAPS[mi]) if transfer else list(range(8))+[9]
        proof=0 if stage==1 else (1 if on else 2) if stage==2 else (3 if transfer else 4)
        refs=[0,4,4] if stage==1 else ([1,2,4] if on else [2,4,4]) if stage==2 else ([0,2,3] if transfer else [0,2,4])
        outputs.append(dict(ops=[p[0] for p in plan],args=[list(p[1:]) for p in plan],
            layout=layout,alias=[layout.index(i) for i in range(8)],eq=[int(eq[a,b]) for a,b in PAIRS],
            owner=[2 if transfer else 1],proof=[proof],premises=refs,
            union_witness=list(UNIONS[ui]) if stage==2 and on else [9,9],gate=[q,r],commands=list(MAPS[mi]),
            payload=[(tag>>b)&1 for b in range(4)],pending=[int(stage==1 and on),int(not transfer)],retired=[int(transfer)]))
    return outputs


def targets(cases):
    rows=[labels(c) for c in cases]
    return {k:np.array([[r[s][k] for r in rows] for s in range(3)],np.int32) for k in SPECS}


def expected(case,stage):
    """Checker builds allowed observations independently of the supervision function."""
    si,ui,mi,on,q,r,tag=map(int,case); eq=checker_eq(case,stage)
    transfer=stage==3 and eq[q,r]
    layout=list(range(8))
    if transfer:
        for i in MAPS[mi]:
            left,right=layout[i:i+2];layout[i:i+2]=[right,left]
        layout=layout[:4]+[8]+layout[4:]
    else:layout.append(9)
    if stage==1:proof,refs=0,[0,4,4]
    elif stage==2:proof,refs=(1,[1,2,4]) if on else (2,[2,4,4])
    else:proof,refs=(3,[0,2,3]) if transfer else (4,[0,2,4])
    return dict(ops=[p[0] for p in SHAPES[si]],args=[list(p[1:]) for p in SHAPES[si]],
        layout=layout,alias=[layout.index(i) for i in range(8)],eq=[int(eq[a,b]) for a,b in PAIRS],
        owner=[2 if transfer else 1],proof=[proof],premises=refs,
        union_witness=list(UNIONS[ui]) if stage==2 and on else [9,9],gate=[q,r],commands=list(MAPS[mi]),
        payload=[(tag>>b)&1 for b in range(4)],pending=[int(stage==1 and on),int(not transfer)],retired=[int(transfer)])


def decode(logits):
    result={}
    for k,(a,b) in OFFSETS.items():
        v=logits[...,a:b].reshape(logits.shape[:-1]+SPECS[k])
        result[k]=(v>=0).astype(np.int32) if k in BOOL else v.argmax(-1)
    return result


def audit(cases,positions,result,weight,bias):
    cpu_logits=cpu_unrotate(result['tokens'],result['locations'])@weight.astype(np.float64).T+bias.astype(np.float64)
    actual=decode(cpu_logits); advertised=decode(result['logits'])
    n=len(cases)
    truth={k:[] for k in SPECS}
    for c in cases:
        for k in SPECS:truth[k].append([])
        for stage in (1,2,3):
            h=expected(c,stage)
            for k in SPECS:truth[k][-1].append(h[k])
    truth={k:np.swapaxes(np.asarray(v),0,1) for k,v in truth.items()}
    equal={k:np.all((actual[k]==truth[k]).reshape(3,n,-1),axis=-1) for k in SPECS}
    binding=np.ones((3,n),bool)
    for k in SPECS:binding &= np.all((actual[k]==advertised[k]).reshape(3,n,-1),axis=-1)
    owner=result['owners']; loc=np.take_along_axis(np.broadcast_to(positions,(3,)+positions.shape),owner[...,None],-1)[...,0]
    binding &= (loc==result['locations']) & (owner==actual['owner'][...,0])
    stage_ok=np.logical_and.reduce(list(equal.values())) & binding
    wanted_transfer=truth['retired'][2,:,0].astype(bool); predicted_transfer=actual['retired'][2,:,0].astype(bool)
    read_ok=np.all(result['read_roles']==np.arange(8),axis=-1)&np.all(result['read_ports']==truth['alias'][2],axis=-1)&result['read_valid']
    read_ok &= np.all(result['read_payload']==truth['payload'][2],axis=-1)&np.all(result['read_eq']==truth['eq'][2],axis=-1)
    finite=np.isfinite(result['tokens']).all(axis=(0,2)) & np.isfinite(result['logits']).all(axis=(0,2))
    full=np.all(stage_ok,axis=0)&read_ok&finite
    eqfalse=(actual['eq']==1)&(truth['eq']==0);eqmiss=(actual['eq']==0)&(truth['eq']==1)
    derived=np.zeros((n,len(PAIRS)),bool)
    for i,c in enumerate(cases):
        direct=UNIONS[c[1]] if c[3] else None
        base=checker_eq(c,1)
        derived[i]=[bool(truth['eq'][1,i,j] and not base[a,b] and (a,b)!=direct) for j,(a,b) in enumerate(PAIRS)]
    derived_cases=derived.any(-1)
    first_fail=[int(np.sum((~stage_ok[s]) & np.all(stage_ok[:s],axis=0))) for s in range(3)]
    examples=[]
    for i in np.flatnonzero(~full)[:3]:
        fields=[k for k in SPECS if not equal[k][:,i].all()]
        examples.append(dict(case=cases[i].tolist(),fields=fields,
            stage2_eq_actual=actual['eq'][1,i].tolist(),stage2_eq_expected=truth['eq'][1,i].tolist(),
            final_alias_actual=actual['alias'][2,i].tolist(),final_alias_expected=truth['alias'][2,i].tolist(),
            transfer_actual=bool(predicted_transfer[i]),transfer_expected=bool(wanted_transfer[i])))
    return dict(cases=n,passed=int(full.sum()),stage_passed=stage_ok.sum(1).tolist(),first_failing_run=first_fail,
        field_trace_passed={k:int(v.all(0).sum()) for k,v in equal.items()},
        cpu_gpu_decisions_agree=bool(binding.all()),reads_passed=int(read_ok.sum()),
        expected_transfers=int(wanted_transfer.sum()),transfer_true_positive=int((wanted_transfer&predicted_transfer).sum()),
        false_transfers=int((~wanted_transfer&predicted_transfer).sum()),missed_transfers=int((wanted_transfer&~predicted_transfer).sum()),
        transfer_alias_passed=int((equal['alias'][2]&wanted_transfer).sum()),
        union_eq_false_positive_bits=int(eqfalse[1].sum()),union_eq_missing_bits=int(eqmiss[1].sum()),
        derived_equality_cases=int(derived_cases.sum()),derived_equality_case_passed=int((equal['eq'][1]&derived_cases).sum()),
        decoded_union_position_passed=int(equal['union_witness'][1].sum()),examples=examples)
