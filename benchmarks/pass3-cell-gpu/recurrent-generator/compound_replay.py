"""Cross two frozen *generated* DAGs with both on-device verifier schedules; run the audit only afterwards."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from capture import inputs, load_catalog, read, verify, execute
from compound_audit import audit, proof_counts
from compound_model import pair_joins


def record_digest(arr):
    return hashlib.sha256(np.ascontiguousarray(arr).view(np.uint8)).hexdigest()


def compare(source, dest):
    for filename, fields in [('neural-output.npz',('raw','verdict','rhs_ordinal')),('compound-output.npz',('claims',)),
                             ('output.npz',('rhs','writes','resumes','runs','unions','parents','meta'))]:
        with np.load(source/filename) as a,np.load(dest/filename) as b:
            for k in fields:
                np.testing.assert_array_equal(a[k],b[k],err_msg=f'{filename}::{k}')


def reject_one_parent(a):
    """Mutate just one generated root; a sibling with an independent parent is a positive control."""
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        image,program,gold=inputs(a.corpus,a.ref,case)
        donor=a.ref/'sum-bits/program.json'
        entries=load_catalog(image,program,donor)
        joins=pair_joins(read(donor))
        seed=1709
        policy=read(a.weights/f'train-{seed}'/'policy.json')
        source=a.paired/f'{case}-{seed}-batch'
        with np.load(source/'compound-output.npz') as c,np.load(source/'neural-output.npz') as n:
            claims=c['claims'];raw=n['raw'].copy();root=n['rhs_ordinal']
        independent=(claims[:,0,7]>0) & (claims[:,1,7]>0) & (claims[:,0,2]!=claims[:,1,2])
        candidates=np.flatnonzero(independent)
        if not len(candidates):
            report[case]=dict(eligible_forks=0);continue
        t=int(candidates[0])
        # First observed two-branch fork, no search for a favorable release outcome.
        damaged=int(claims[t,0,0]);other=int(claims[t,1,0])
        assert damaged!=other and raw[t,damaged,11]==1
        raw[t,damaged,9]=0  # encoded row zero decodes to -1, while the root remains active.
        dest=a.out/f'{case}-{seed}-batch'
        cfg=dict(catalog=entries,rows=2,hidden=8,ranks=8,waves=2,weights=policy['roots'],
                 compound=dict(joins=joins,child=policy['child'],batch=True,replay=raw))
        execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,neural=cfg,count_work=True)
        verify(dest,gold,image)
        with np.load(dest/'neural-output.npz') as n,np.load(dest/'compound-output.npz') as c:
            after=c['claims']
            np.testing.assert_array_equal(n['raw'],raw)
            assert n['verdict'][t,damaged,0]==2 and n['rhs_ordinal'][t,damaged]==0
            assert after[t,0,8]==1 and after[t,0,2]==0 and after[t,0,7]==0
            assert n['rhs_ordinal'][t,other]==root[t,other]
            for field in (0,1,2,3,4,5,7,8):
                assert after[t,1,field]==claims[t,1,field]
            changed=np.argwhere(after[:,:,7]!=claims[:,:,7]).tolist()
            report[case]=dict(seed=seed,eligible_forks=len(candidates),issue_run=t+1,masked_parent_row=damaged,
                              masked_parent_original_rhs=int(root[t,damaged]),orphaned_child_original_rhs=int(claims[t,0,7]),
                              surviving_parent_row=other,surviving_parent_rhs=int(root[t,other]),surviving_child_rhs=int(after[t,1,7]),
                              changed_child_winner_slots=[[run+1,lane] for run,lane in changed],
                              all_source_outputs_aligned=True)
        print(case,report[case],flush=True)
    (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        image,program,gold=inputs(a.corpus,a.ref,case)
        donor=a.ref/'sum-bits/program.json'
        entries=load_catalog(image,program,donor)
        joins=pair_joins(read(donor))
        for seed in a.seeds:
            weights=a.weights/f'train-{seed}'
            policy=read(weights/'policy.json')
            assert policy['joins']==list(map(list,joins))
            for generated in a.generated:
                source=a.paired/f'{case}-{seed}-{generated}'
                previous=audit(source,image,gold,entries,donor,weights,a.receipts/case,a.publications/case,
                               batch=generated=='batch')
                with np.load(source/'neural-output.npz') as z:
                    # root/child token payload alone. The GPU decodes the join anew from these addresses.
                    raw=z['raw']
                schedules={}
                for verifier in ('wave','batch'):
                    dest=a.out/f'{case}-{seed}-{generated}-{verifier}'
                    cfg=dict(catalog=entries,rows=2,hidden=8,ranks=8,waves=2,weights=policy['roots'],
                             compound=dict(joins=joins,child=policy['child'],batch=verifier=='batch',replay=raw))
                    execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,neural=cfg,count_work=True)
                    verify(dest,gold,image)
                    compare(source,dest)
                    counts=proof_counts(dest,entries,joins)
                    roles=read(dest/'run.json')['execution_roles']
                    assert not roles['recurrent_neural_token_input'] and roles['binding_generator'].startswith('frozen')
                    assert roles['rhs_inputs_from_recurrent_neural_proposals']==0
                    assert roles['rhs_inputs_from_frozen_proposals']==counts['neural_children']+counts['neural_roots']
                    assert counts['neural_children']==previous['neural_children'] and counts['neural_roots']==previous['neural_roots']
                    with np.load(dest/'compound-output.npz') as z:claim_hash=record_digest(z['claims'])
                    schedules[verifier]=dict(claims_sha256=claim_hash,source_aligned=True,
                                            verified_child_ordinals=counts['neural_children'],
                                            remaining_exact=counts['exact_residual'],
                                            work=read(dest/'run.json')['neural_work_counts'])
                assert schedules['wave']==schedules['batch']
                key=f'{case}/{seed}/{generated}'
                report[key]=dict(actual=previous,frozen_raw_sha256=record_digest(raw),replays=schedules)
                (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
                print(key,previous['neural_roots'],previous['neural_children'],previous['pytorch']['max_latent_difference'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','receipts','publications','weights','paired','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--generated',nargs='+',choices=('wave','batch'),default=['wave','batch'])
    p.add_argument('--reject-one-parent',action='store_true')
    args=p.parse_args()
    if args.reject_one_parent:reject_one_parent(args)
    else:run(args)
