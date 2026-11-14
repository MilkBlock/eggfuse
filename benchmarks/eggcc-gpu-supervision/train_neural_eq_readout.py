"""Train floating-token semantic readout with synthetic exact completion labels.

The finite interface matching head is frozen. Eq proposals are not committed;
raw and transitively closed mistakes, plus zero-token ablation, are reported.
"""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_eq_readout import EqReadout,masked_loss,metrics
from neural_ordered_relations import ordered_model
from neural_cell_samples import samples
from train_neural_cell_chains import build,chain_loss,rollout,fingerprints


class CompletionReadout(nn.Module):
    def __init__(self,input_width,relation_width,slot_width):
        super().__init__();self.cell=ordered_model(input_width,relation_width,True);self.eq=EqReadout(slot_width)
        self.cell.relation.freeze();self.cell.match_relation.freeze()


def objective(model,batch,parent,chain):
    base=chain_loss(model.cell,batch,parent,chain)
    _,token=model.cell(batch['x'],batch['edges'],batch['mask'],batch['request'],batch['relations'])
    _,_,next_token=rollout(model.cell,parent,chain)
    return base+masked_loss(model.eq(token,batch['request']),batch['eq_target'],batch['eq_mask'])+masked_loss(model.eq(next_token,chain['request']),chain['eq_target'],chain['eq_mask'])


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path);p.add_argument('--steps',type=int,default=800);p.add_argument('--evaluate-only',action='store_true');a=p.parse_args()
    if a.steps<1:raise ValueError('positive steps required')
    source=json.loads(a.trace.read_text());source=source.get('recipe',source)
    recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context']);width=max(len(r['slots']) for r in recipe['rules']);started=time.perf_counter()
    base,chain,coverage=build(recipe,8,23001,ordered=True,eq_targets=True)
    test,tc,test_coverage=build(recipe,4,93003,ordered=True,eq_targets=True)
    direct=samples(recipe,128,77717,ordered=True,eq_targets=True)
    seen=set(fingerprints(base,chain));overlap=np.array([v in seen for v in fingerprints(test,tc)])
    device=lambda d:{k:mx.array(v) for k,v in d.items()}
    db,dc,dd,dt,de=map(device,(base,chain,direct,test,tc))
    mx.random.seed(117);model=CompletionReadout(direct['x'].shape[-1],direct['relations'].shape[-1],width);(model.load_weights if a.evaluate_only else model.cell.load_weights)(str(a.weights))
    from mlx.utils import tree_flatten
    frozen_before={k:np.array(v).copy() for k,v in tree_flatten(model.cell.parameters()) if k.startswith(('relation.','match_relation.'))}
    def evaluate():
        parent={k:v[de['parent']] for k,v in dt.items()};first,second,token=rollout(model.cell,parent,de)
        actual=model.eq(token,de['request']);teacher=model.eq(de['target'],de['request']);zero=model.eq(mx.zeros_like(token),de['request']);mx.eval(first,second,actual,teacher,zero)
        pos=tc['valid'];labels=tc['eq_target'][pos];mask=tc['eq_mask'][pos]
        perm=np.arange(len(pos))
        for rid in np.unique(tc['consumer']):
            indices=np.flatnonzero(pos&(tc['consumer']==rid));perm[indices]=np.roll(indices,1)
        shuffled=model.eq(token[mx.array(perm)],de['request']);mx.eval(shuffled)
        changed=pos&np.any((tc['eq_target'][perm]!=tc['eq_target'])&tc['eq_mask'],axis=1)
        novel=pos&~overlap
        return dict(unseen_states=int(novel.sum()),unseen_predicted_token=metrics(np.array(actual)[novel],tc['eq_target'][novel],tc['eq_mask'][novel],width),shuffled_within_template=metrics(np.array(shuffled)[pos],labels,mask,width),shuffled_semantically_changed_states=int(changed.sum()),predicted_token=metrics(np.array(actual)[pos],labels,mask,width),teacher_token=metrics(np.array(teacher)[pos],labels,mask,width),zero_token=metrics(np.array(zero)[pos],labels,mask,width),matching_errors=int((((np.array(first)>=0)&(np.array(second)>=0))!=pos).sum()))
    before=evaluate();print(json.dumps(dict(before=before)),flush=True)
    grad=nn.value_and_grad(model,objective);optimizer=optim.Adam(learning_rate=5e-4);rng=np.random.default_rng(119)
    for step in range(0 if a.evaluate_only else a.steps):
        bi=mx.array(rng.integers(len(direct['valid']),size=128));ci=mx.array(rng.integers(len(chain['valid']),size=64))
        batch={k:v[bi] for k,v in dd.items()};c={k:v[ci] for k,v in dc.items()};parent={k:v[c['parent']] for k,v in db.items()}
        value,g=grad(model,batch,parent,c);optimizer.update(model,g);mx.eval(value,model.parameters(),optimizer.state)
        if step%100==0:print(json.dumps(dict(step=step,loss=float(value))),flush=True)
    after=evaluate();current=dict(tree_flatten(model.cell.parameters()))
    frozen_unchanged=all(np.array_equal(v,np.array(current[k])) for k,v in frozen_before.items())
    if not frozen_unchanged:raise AssertionError('interface predicate weights changed')
    model.save_weights(str(a.output.with_suffix('.safetensors')))
    transition=a.output.with_suffix('.transition.safetensors');model.cell.save_weights(str(transition))
    readout=a.output.with_suffix('.eq.safetensors');model.eq.save_weights(str(readout))
    report=dict(scope='semantic Eq readout from floating generated tokens; standalone synthetic two-step evaluation, no graph mutations',synthetic_only_training=True,slot_width=width,pair_outputs=width*(width-1)//2,training_direct_samples=len(direct['valid']),evaluation_chain_feature_overlap=int(overlap.sum()),training_coverage=coverage,test_coverage=test_coverage,before=before,after=after,steps=0 if a.evaluate_only else a.steps,evaluation_only=a.evaluate_only,interface_head_unchanged=frozen_unchanged,readout_receives_exact_ids=False,readout_receives_incidence=False,semantic_proposals_committed=False,promoted_as_default=False,wall_seconds=time.perf_counter()-started,parent_weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest(),transition_weights_sha256=hashlib.sha256(transition.read_bytes()).hexdigest(),readout_weights_sha256=hashlib.sha256(readout.read_bytes()).hexdigest(),limitations=['Known bounded synthetic chain family; not arbitrary graphs or new rulesets','Zero-token ablation removes both dynamic contents and the usual token distribution','Template request also carries information; readout is not token-only','False positive Eq proposals would corrupt semantics if committed without correction'])
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(after))


if __name__=='__main__':main()
