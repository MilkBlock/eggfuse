"""Learn combined ownership tokens from synthetic, effect-backed Cell pairs.

Source and destination Eq projections are decoded from the same generated token.
No exact result IDs enter the readout. This is not an autonomous GPU runtime.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_cell_samples import samples
from neural_cell_chains import chains
from neural_eq_readout import EqReadout,masked_loss,metrics
from neural_ordered_relations import ordered_model
from train_neural_cell_chains import rollout,chain_loss,fingerprints


class CombinedOwner(nn.Module):
    def __init__(self,input_width,relation_width,width):
        super().__init__()
        self.cell=ordered_model(input_width,relation_width,True)
        self.cell.relation.freeze();self.cell.match_relation.freeze()
        self.eq=EqReadout(width)


def build(recipe,count,seed,ordered_request=True):
    records=[];base=samples(recipe,count,seed,records,ordered=True)
    chain,coverage=chains(recipe,records,ordered=True,eq_targets=True,combined_owner=True,ordered_owner_request=ordered_request)
    return base,chain,coverage


def objective(model,batch,parent,chain):
    _,_,token=rollout(model.cell,parent,chain)
    return chain_loss(model.cell,batch,parent,chain)+masked_loss(model.eq(token,chain['request']),chain['eq_target'],chain['eq_mask'])


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--steps',type=int,default=1200);p.add_argument('--unordered-request',action='store_true');a=p.parse_args()
    if a.steps<1:raise ValueError('positive training steps')
    source=json.loads(a.trace.read_text());source=source.get('recipe',source)
    recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context'])
    began=time.perf_counter();base,chain,coverage=build(recipe,8,23001,not a.unordered_request);test,tc,test_coverage=build(recipe,4,93003,not a.unordered_request)
    width=2*max(len(r['slots']) for r in recipe['rules'])
    seen=set(fingerprints(base,chain));overlap=np.array([x in seen for x in fingerprints(test,tc)])
    device=lambda d:{k:mx.array(v) for k,v in d.items()}
    db,dc,dt,de=map(device,(base,chain,test,tc))
    mx.random.seed(117);model=CombinedOwner(base['x'].shape[-1],base['relations'].shape[-1],width)
    model.cell.load_weights(str(a.weights))
    from mlx.utils import tree_flatten
    frozen={k:np.array(v) for k,v in tree_flatten(model.cell.parameters()) if k.startswith(('relation.','match_relation.'))}
    def evaluate(b,c):
        scores=[];accept=[];errors=[];zero=[]
        for start in range(0,len(c['valid']),128):
            cc=device({k:v[start:start+128] for k,v in c.items()});parent=device({k:v[c['parent'][start:start+128]] for k,v in b.items()})
            first,second,t=rollout(model.cell,parent,cc);eq=model.eq(t,cc['request']);z=model.eq(mx.zeros_like(t),cc['request'])
            mx.eval(first,second,t,eq,z)
            scores.append(np.array(eq));zero.append(np.array(z));accept.append((np.array(first)>=0)&(np.array(second)>=0));errors.append(np.mean((np.array(t)-c['target'][start:start+128])**2,axis=1))
        score=np.concatenate(scores);pos=c['valid'];report=dict(matching_errors=int((np.concatenate(accept)!=pos).sum()),token_mse=float(np.concatenate(errors)[pos].mean()))
        for name,key in [('combined','eq_mask'),('source_entry','source_eq_mask'),('target_entry','target_eq_mask')]:
            report[name]=metrics(score[pos],c['eq_target'][pos],c[key][pos],width)
        report['zero_token']=metrics(np.concatenate(zero)[pos],c['eq_target'][pos],c['eq_mask'][pos],width)
        return report,score
    before,_=evaluate(test,tc);print(json.dumps(dict(before=before,coverage=coverage)),flush=True)
    grad=nn.value_and_grad(model,objective);opt=optim.Adam(learning_rate=5e-4);rng=np.random.default_rng(119)
    for step in range(a.steps):
        ci=mx.array(rng.integers(len(chain['valid']),size=64));bi=mx.array(rng.integers(len(base['valid']),size=128))
        c={k:v[ci] for k,v in dc.items()};parent={k:v[c['parent']] for k,v in db.items()};batch={k:v[bi] for k,v in db.items()}
        loss,g=grad(model,batch,parent,c);opt.update(model,g);mx.eval(loss,model.parameters(),opt.state)
        if step%100==0:print(json.dumps(dict(step=step,loss=float(loss))),flush=True)
    after,scores=evaluate(test,tc);training,_=evaluate(base,chain);novel=tc['valid']&~overlap
    after['unseen']=metrics(scores[novel],tc['eq_target'][novel],tc['eq_mask'][novel],width)
    current=dict(tree_flatten(model.cell.parameters()));unchanged=all(np.array_equal(v,np.array(current[k])) for k,v in frozen.items())
    if not unchanged:raise AssertionError('matching weights changed')
    model.save_weights(str(a.output.with_suffix('.safetensors')));model.cell.save_weights(str(a.output.with_suffix('.transition.safetensors')));model.eq.save_weights(str(a.output.with_suffix('.eq.safetensors')))
    report=dict(scope='standalone GPU synthetic combined-owner token training and source/destination Eq projections; no runtime commits',synthetic_only_training=True,backpropagation=True,ordered_owner_request=not a.unordered_request,slot_width=width,train=coverage,test=test_coverage,test_input_overlap=int(overlap.sum()),before=before,after=after,training=training,steps=a.steps,interface_head_unchanged=unchanged,wall_seconds=time.perf_counter()-began,parent_weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest(),limitations=['Fixed two-step input routing, not device-discovered third-step consumption','Combined state is decoded for evaluation, not committed to the graph','Synthetic context rules only; no full ruleset saturation','One 128-float token per combined pair; growth with information is unresolved','Descriptor records completed facts and cannot replace original effect/Run scheduling'])
    report['semantic_status']='pass' if after['combined']['closed_exact_states']==after['combined']['states'] and after['matching_errors']==0 else 'difference'
    report['promoted_for_execution']=False
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(after),flush=True)


if __name__=='__main__':main()
