"""Consume an installed GPU frame across a declared ruleset before CPU audit.

This evaluates the next floating transition; it does not install its outputs
or certify saturation. CPU labels never enter evaluate().
"""
from copy import deepcopy
import numpy as np
import mlx.core as mx
from neural_device_candidates import compile_candidates,candidates
from audit_snapshot_queries import device
from neural_cell_samples import apply_instance
from neural_cell_chains import completed
from neural_eq_readout import targets,metrics


def evaluate(local,state,frames,rules,model,eq_head,atoms,fields):
    outputs=[]
    for rule in rules:
        plan=compile_candidates(local,rule,atoms=atoms,fields=fields,compact_constants=True)
        batch=candidates(state,frames,device(plan),mx.array(True),mx.array(True),mx)
        logits,tokens=model.transition(batch['tokens'],batch['edges'],batch['mask'],batch['request'],batch['relations'])
        scores=eq_head(tokens,batch['request'])
        finite=mx.isfinite(logits)&mx.all(mx.isfinite(tokens),axis=-1)&mx.all(mx.isfinite(scores),axis=-1)
        accepted=batch['live']&batch['constraints_satisfied']&(logits>=0)&finite
        mx.eval(batch,accepted,scores,finite)
        # This standalone audit materializes results, never teacher inputs.
        outputs.append((plan,np.array(accepted),np.array(batch['binding_roots']),np.array(scores),
                        bool(batch['complete']),int(mx.sum(batch['live']&~finite)),
                        np.array(batch['sources']),np.array(batch['mask'])))
    return outputs


def audit(outputs,rules,reference,identities,width,new_rows):
    counts=dict(fourth_rules=len(rules),fourth_expected=0,fourth_observed=0,fourth_missed=0,
                fourth_false_positive=0,fourth_incomplete=0,fourth_nonfinite=0,
                fourth_states=0,fourth_wrong_states=0,fourth_false_merge_states=0,
                fourth_consumed_new_frame=0,fourth_new_frame_wrong_states=0)
    for rule,(plan,accepted,roots,scores,complete,nonfinite,sources,mask) in zip(rules,outputs):
        expected={tuple(sorted(b.items())) for b in reference.matches(rule)};observed=set()
        counts['fourth_expected']+=len(expected);counts['fourth_incomplete']+=not complete
        counts['fourth_nonfinite']+=nonfinite
        for row in np.flatnonzero(accepted):
            if any(int(v) not in identities for v in roots[row]):
                counts['fourth_false_positive']+=1;continue
            key=tuple((s,identities[int(v)]) for s,v in zip(plan['inputs'],roots[row]))
            if key not in expected:counts['fourth_false_positive']+=1;continue
            observed.add(key)
            ref=deepcopy(reference);bound=dict(key);apply_instance(ref,rule,bound)
            target=targets(rule,completed(rule,bound,ref),ref,width)
            result=metrics(scores[row:row+1],target['eq_target'][None,:],target['eq_mask'][None,:],width)
            wrong=1-result['closed_exact_states']
            uses_new=bool(np.any(np.isin(sources[row],new_rows)&mask[row]))
            counts['fourth_states']+=1;counts['fourth_wrong_states']+=wrong
            counts['fourth_false_merge_states']+=result['states_with_false_merge']
            counts['fourth_consumed_new_frame']+=uses_new
            counts['fourth_new_frame_wrong_states']+=uses_new*wrong
        counts['fourth_observed']+=len(observed);counts['fourth_missed']+=len(expected-observed)
    return counts
