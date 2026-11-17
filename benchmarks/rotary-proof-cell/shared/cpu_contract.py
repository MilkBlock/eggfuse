"""CPU-only decoder of the generated structured latent, followed by source audit."""
import numpy as np
from abi import *
from contract import cpu_unrotate
from semantics import expected,decode,checker_eq
from spec import UNIONS
EPS=1e-6

def cpu_scores(tokens,locations):
    shape=tokens.shape[:-1];h=cpu_unrotate(tokens,locations).reshape(-1,TOKEN_WIDTH);n=len(h)
    eq=h[:,:64].reshape(n,8,8);ptr=h[:,64:136].reshape(n,8,9);seed=h[:,136:275]
    phase=h[:,275:278].argmax(-1);gate=h[:,278:279]
    d={k:seed[:,a:b].reshape((n,)+dims) for k,(a,b,dims) in PARTS.items()}
    stage1=phase==0;stage2=phase==1;transfer=(gate[:,0]>.5)&(phase==2);on=d['on'][:,0]>.5
    def cat(p):return np.log(np.maximum(p,EPS))
    def bit(p):return np.log(np.maximum(p,EPS))-np.log(np.maximum(1-p,EPS))
    proof=np.where(stage1,0,np.where(stage2,np.where(on,1,2),np.where(transfer,3,4)))
    refs=np.stack((np.where(stage1,0,np.where(stage2,np.where(on,1,2),0)),
                   np.where(stage1,4,np.where(stage2,np.where(on,2,4),2)),np.where((phase==2)&transfer,3,4)),-1)
    uw=np.concatenate((d['union'],np.zeros((n,2,2))),-1)
    uw=np.where((stage2&on)[:,None,None],uw,np.broadcast_to(np.eye(10)[9],(n,2,10)))
    alias=np.concatenate((ptr,np.zeros((n,8,1))),-1)
    layout=np.concatenate((ptr.swapaxes(-1,-2),gate[:,None,:]*np.eye(9)[4][None,:,None],
                           (1-gate[:,None,:])*np.eye(9)[8][None,:,None]),-1)
    v=dict(ops=cat(d['ops']),args=cat(d['args']),layout=cat(layout),alias=cat(alias),
        eq=bit(np.stack([eq[:,i,j] for i,j in PAIRS],-1)),owner=cat(np.eye(3)[np.where(transfer,2,1)][:,None,:]),
        proof=cat(np.eye(5)[proof][:,None,:]),premises=cat(np.eye(5)[refs]),union_witness=cat(uw),
        gate=cat(np.concatenate((d['query'],np.zeros((n,2,2))),-1)),commands=cat(d['commands']),
        payload=bit(d['payload']),pending=bit(np.stack((stage1&on,~transfer),-1).astype(float)),retired=bit(transfer[:,None].astype(float)))
    return np.concatenate([v[k].reshape(n,-1) for k in SPECS],-1).reshape(shape+(WIDTH,))


def audit(cases,positions,result):
    cpu_logits=cpu_scores(result['tokens'],result['locations'])
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
