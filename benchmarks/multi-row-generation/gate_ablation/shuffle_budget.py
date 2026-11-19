"""Diagnostic: transplant learned whole gate schedules at exactly matched slot budgets."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from evaluate import models_for, transfer, EClassSchema
from gate_data import templates, fresh_panel
from audit_gate import verify_token
from eclass_ablation.data import audit
from credit_ablation.reward import team_reward


def donor_indices(data,rng,same_state):
    # Every slot histogram is exactly preserved; masks are reassigned to another source group.
    groups=np.unique(data['group_id'])
    permutation=np.arange(len(groups)); shifts=np.zeros(len(groups),int)
    if same_state:
        for blind in (0,1):
            bucket=np.array([i for i,g in enumerate(groups) if data['blind'][np.flatnonzero(data['group_id']==g)[0]]==blind])
            cycle=rng.permutation(bucket);permutation[cycle]=np.roll(cycle,-1)
    else:
        cycle=rng.permutation(len(groups));permutation[cycle]=np.roll(cycle,-1)
        shifts=rng.integers(0,8,len(groups))
    ids=np.empty(len(data['a']),int)
    for i,group in enumerate(groups):
        local=np.flatnonzero(data['group_id']==group)
        donor=np.flatnonzero(data['group_id']==groups[permutation[i]])
        ids[local]=np.roll(donor,int(shifts[i]))
    assert len(set(ids))==len(ids) and np.all(data['group_id']!=data['group_id'][ids])
    if same_state:
        for key in ('state','variant','blind'):np.testing.assert_array_equal(data[key],data[key][ids])
    return ids


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('parent',type=Path);a=p.parse_args()
    ts=templates();schema=EClassSchema([t for t in ts if t['split']=='train']);dev=torch.device('mps')
    models,_=models_for(a.root,a.parent,schema,dev)
    main_report=json.loads((a.root/'results.json').read_text());records={}
    with torch.inference_mode():
        for t in (t for t in ts if t['split']=='heldout'):
            tid=t['id'];d=fresh_panel(t);ready=transfer(d,slice(None),dev)
            target=[torch.as_tensor(d[k],device=dev) for k in ('target1','target2')]
            for seed in (1703,1709):
                name=f'gate_p25-{seed}';m=models[name];table=m.encoder.frozen_bank(schema.bank(t,'pairwise',dev))
                lane=f'p25-calibrated-metal_skip-{seed}'
                with np.load(a.root/'traces'/f'{tid}-{lane}.npz') as z:
                    gates=np.stack((z['0_gate_open'],z['1_gate_open']),axis=1).astype(bool)
                def trial(mask,verify):
                    st,token,rel=m(*ready,table,mode='all',backend='metal_skip',gate_override=torch.as_tensor(mask,device=dev))
                    _,parts=team_reward(*st,*target)
                    ans=dict(complete=int(parts['E2'].sum()),missing=int(parts['run2_missing'].sum()),duplicates=int(parts['run2_duplicates'].sum()),
                             open_by_run=mask.sum((0,2)).tolist())
                    if verify:
                        decoded=[{k:s[k].cpu().numpy() for k in ('active','pointers','rows','gate_open')} for s in st]
                        verify_token(d,*decoded,token.cpu().numpy(),None)
                        out=audit(d,*decoded)['run2']
                        assert (out['complete_graphs'],out['duplicates'],out['missing'])==(ans['complete'],ans['duplicates'],ans['missing'])
                    return ans
                original=trial(gates,True)
                assert original['complete']==main_report['panels'][tid][lane]['r2']['complete_graphs']
                item={'original':original}
                for tag in ('across_state','within_state'):
                    draws=[]
                    for i in range(16):
                        ids=donor_indices(d,np.random.default_rng(6500+i),tag=='within_state')
                        alt=gates[ids];np.testing.assert_array_equal(alt.sum(0),gates.sum(0))
                        draws.append(trial(alt,i==0))
                    item[tag]=draws
                records[f'{tid}/{name}']=item
    (a.root/'shuffle-budget.json').write_text(json.dumps(records,indent=2)+'\n')
    for seed in (1703,1709):
        chosen=[v for n,v in records.items() if n.endswith(str(seed))]
        print(seed,sum(x['original']['complete'] for x in chosen), {tag:[sum(x[tag][i]['complete'] for x in chosen) for i in range(16)] for tag in ('across_state','within_state')})
if __name__=='__main__':main()
