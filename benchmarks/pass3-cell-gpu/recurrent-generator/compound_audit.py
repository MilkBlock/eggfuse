"""Post-run audit of recurrent two-row parents and their cross-Run Bake continuations."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import torch

from capture import inputs, load_catalog, read, verify
from compound_model import CompoundActor, pair_joins
from feedback import training_reply
from model import HIDDEN, ROWS


def check_tokens(raw, verdict, claims, entries, weights, policy, receipt_capture, *, batch):
    """Reconstruct the entire assisted actor rollout from zeros and captured causal observations."""
    model = CompoundActor(policy['joins'])
    model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
    model.eval()
    # Compatible root entries have already been masked in the causal observations.
    # Each transferred join additionally requires the child's leaf to exist in this program.
    with torch.no_grad():
        for join_id, (_, _, _, right) in enumerate(policy['joins']):
            if entries[right][0] < 0:
                model.row_score[:, join_id] = -1e6
    with np.load(receipt_capture/'training.npz') as z:
        features = torch.from_numpy(z['features'])
        suffix_outcomes = torch.from_numpy(z['receipt'])
    assert len(features) == len(raw)
    previous = torch.zeros(1, ROWS, HIDDEN+4)
    max_error = 0.
    ambiguous = 0
    latent_changed = 0
    for i in range(len(raw)):
        _, parents = model.root.step(features[i:i+1], previous)
        labels = suffix_outcomes[i:i+1]
        reply, _ = training_reply(parents, labels, torch.zeros_like(labels,dtype=torch.bool))
        actual_reply = verdict[i,:ROWS]
        np.testing.assert_array_equal(reply[0,:,:3], actual_reply[:,:3], err_msg=f'parent verification in Run {i+1}')
        mask = (actual_reply[:,0]==2) & (actual_reply[:,3]<-1)
        np.testing.assert_array_equal(reply[0,:,3].numpy()[mask], actual_reply[mask,3])
        if batch:
            # A pending child can use only its parents' token. Remove the receipt values entirely.
            reply = torch.zeros_like(reply)
        logits, previous, action = model.propose_children(parents,reply,not batch,torch.tensor([i+1]))
        # Paired local intervention on identical parent identities, receipts and source Run.
        # This is a post-run policy readout. Its alternate children do not enter the graph.
        masked = parents.clone()
        masked[...,:HIDDEN] = 0
        _, _, without_hidden = model.propose_children(masked, reply, not batch, torch.tensor([i+1]))
        latent_changed += int((without_hidden!=action).sum())
        expected = torch.cat((parents,previous),dim=1)[0].numpy()
        np.testing.assert_array_equal(expected[:,HIDDEN:],raw[i,:,HIDDEN:],err_msg=f'neural token in Run {i+1}')
        error = float(np.abs(expected[:,:HIDDEN]-raw[i,:,:HIDDEN]).max())
        assert np.isfinite(error) and error < .002,(i+1,error)
        max_error = max(max_error,error)
        sorted_scores = logits.topk(2,-1).values
        ambiguous += int((sorted_scores[:,:,0]-sorted_scores[:,:,1]<1e-5).sum())
        chosen=action[0].numpy()
        expected_join=np.where(chosen>0, (chosen-1)%len(policy['joins']),-1)
        np.testing.assert_array_equal(expected_join,claims[i,:,1],err_msg=f'compiled join in Run {i+1}')
    return dict(runs=len(raw),discrete_differences=0,max_latent_difference=max_error,
                close_child_score_pairs=ambiguous,one_step_child_decisions_changed_by_masking_parent_latent=latent_changed,
                starts_at_zero=True,
                feedback='none_before_children' if batch else 'reconstructed_root_verdicts')


def proof_counts(folder, entries, joins, *, published=None, consumed=None, reference_rhs=None, reference_pivot=None):
    """Identify distinct actual winners. A child is credited only if its emitted parent won."""
    with np.load(folder/'neural-output.npz') as n:
        raw, verdict, root_order = [n[k] for k in ('raw','verdict','rhs_ordinal')]
    with np.load(folder/'compound-output.npz') as c:
        claims=c['claims']
    with np.load(folder/'output.npz') as g:
        rhs,run_table=g['rhs'],g['runs']
    nruns=len(run_table)
    assert raw.shape==(nruns,4,12) and claims.shape==(nruns,2,11)
    assert root_order.shape==(nruns,4) and not root_order[:,2:].any()
    root_events=root_order[:,:ROWS]
    submitted=set()
    last_publication={}
    if published is not None:
        for ordinal,_,row,_ in published:
            last_publication[int(row)]=int(ordinal)
    later_republished=0
    source_matches=0
    same_reference_source=0
    for t,row in zip(*np.nonzero(root_events)):
        ordinal=int(root_events[t,row])
        leaf,addr,rank,active=map(int,raw[t,row,-4:])
        assert active==1 and 1<=rank<=8 and verdict[t,row,0]==1
        assert tuple(rhs[ordinal-1,[0,1,3]])==(t+1,entries[leaf-1][0],addr-1)
        assert ordinal not in submitted
        submitted.add(ordinal)
    parent_wins=len(submitted)
    status=claims[...,8]
    examples=[]
    parents_with_children=set()
    cross_lane=0
    lag=Counter()
    for t,lane in zip(*np.nonzero(status)):
        parent,j,ordinal,row,ticket,boundary,bank,winner,state,attempts,_=map(int,claims[t,lane])
        assert parent in range(ROWS) and j in range(len(joins)) and 1<=state<=6
        _,left,port,right=joins[j]
        assert int(raw[t,parent,-4])==left+1
        np.testing.assert_array_equal(raw[t,ROWS+lane,-4:], [right+1,t*ROWS+parent+1,port+1,1])
        if state==1:
            assert ordinal==ticket==boundary==winner==0
            continue
        assert 0<ordinal<=len(rhs) and ordinal==root_events[t,parent] and ticket>0
        assert rhs[ordinal-1,0]==t+1 and rhs[ordinal-1,1]==entries[left][0]
        if published is not None:
            receipt=tuple(map(int,published[ticket-1]))
            assert receipt==(ordinal,port,row,entries[right][3]),(t+1,lane,'published',ticket,receipt)
            source_matches+=1
        if state in (2,3,4):
            assert winner==0 and boundary==0
            continue
        assert t+1<boundary<=nruns and attempts>0 and bank>=0
        if state==5:
            assert winner==0
            continue
        assert 0<winner<=len(rhs) and tuple(rhs[winner-1,[0,1,3]])==(boundary,entries[right][0],row)
        assert winner not in submitted
        submitted.add(winner)
        # A later publication to the same physical row cannot explain the earlier reference.
        # This counts observed publications, not inferred lack of validity in the final graph.
        later_republished += int(last_publication.get(row,0)>winner)
        parents_with_children.add(ordinal)
        cross_lane += int(parent != lane)
        lag[boundary-t-1] += 1
        if consumed is not None:
            # Other legal origins can win RHS dedup. The frozen source ticket can only be
            # compared when the committed reference used the same anchor and leaf.
            if reference_rhs[winner-1,3]==row and reference_pivot[winner-1]==entries[right][1]+1:
                assert consumed[winner-1]==ticket,(t+1,lane,'consumed',winner,ticket,int(consumed[winner-1]))
                same_reference_source+=1
        if len(examples)<3:
            examples.append(dict(issue_run=int(t)+1,child_row=int(lane),parent_row=parent,join=j,parent_rhs=ordinal,
                                 effect_port=port,physical_row=row,ticket=ticket,release_run=boundary,child_rhs=winner))
    child_wins=len(submitted)-parent_wins
    credited_ordinals=np.fromiter(sorted(submitted),dtype=np.int64)
    neurons_by_run=np.bincount(rhs[credited_ordinals-1,0].astype(int),minlength=nruns+1)[1:]
    counts=run_table[:,1]
    assert (neurons_by_run<=counts).all()
    root_codes=verdict[:,:2,0]
    np.testing.assert_array_equal(raw[:,:2,-1]>0,root_codes!=0)
    np.testing.assert_array_equal(raw[:,2:,-1]>0,status!=0)
    return dict(runs=nruns,rhs=len(rhs),neural_roots=parent_wins,neural_children=child_wins,
                exact_residual=len(rhs)-len(submitted),source_verified_publications=source_matches,
                same_reference_winner_ticket=same_reference_source,
                winning_children_whose_input_row_is_republished_later=later_republished if published is not None else None,
                root_raw=int((root_codes!=0).sum()),root_verdict_counts=dict(Counter(map(int,root_codes.flatten()))),
                child_raw=int((status!=0).sum()),child_state_counts=dict(Counter(map(int,status.flatten()))),
                child_route_attempts=int(claims[...,9].sum()),distinct_winning_parents=len(parents_with_children),
                winners_referencing_peer_row=cross_lane,release_lag_in_source_runs={int(k):v for k,v in lag.items()},
                nonempty=int((counts>0).sum()),fully_neural_nonempty=int(((counts>0)&(counts==neurons_by_run)).sum()),
                examples=examples)


@torch.inference_mode()
def audit(folder,image,gold,entries,donor,model_dir,receipt_capture,composition_capture,*,batch):
    torch.set_num_threads(1)
    policy=read(model_dir/'policy.json')
    joins=pair_joins(read(donor))
    assert list(map(list,joins))==policy['joins']
    verify(folder,gold,image)
    with np.load(composition_capture/'neural-inputs.npz') as p, np.load(composition_capture/'output.npz') as g:
        counts=proof_counts(folder,entries,joins,published=p['publications'],consumed=p['consumed'],reference_rhs=g['rhs'],reference_pivot=p['pivot'])
    with np.load(folder/'neural-output.npz') as n,np.load(folder/'compound-output.npz') as c:
        counts['pytorch']=check_tokens(n['raw'],n['verdict'],c['claims'],entries,model_dir/'actor.pt',policy,receipt_capture,batch=batch)
    counts['source_aligned']=True
    return counts


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','receipts','publications','weights','trial','out'):p.add_argument(k,type=Path)
    p.add_argument('--case',required=True)
    p.add_argument('--batch',action='store_true')
    args=p.parse_args()
    image,program,gold=inputs(args.corpus,args.ref,args.case)
    donor=args.ref/'sum-bits/program.json'
    entries=load_catalog(image,program,donor)
    stats=audit(args.trial,image,gold,entries,donor,args.weights,args.receipts/args.case,args.publications/args.case,batch=args.batch)
    args.out.write_text(json.dumps(stats,indent=1)+'\n')
    print(args.case,stats['neural_roots'],stats['neural_children'],stats['exact_residual'],flush=True)
