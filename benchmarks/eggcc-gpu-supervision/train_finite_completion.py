"""Fit the enumerated local domain through generated source tokens on MLX GPU.

Reports training-domain fitting, not held-out generalization or runtime proof.
"""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from device_stage_models import select_ruleset
from finite_entry_domain import input_cases
from neural_cell_samples import samples
from neural_cell_chains import chains
from train_neural_cell_chains import rollout
from train_neural_eq_readout import CompletionReadout,objective
from neural_eq_readout import metrics


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--ruleset',default='canon');p.add_argument('--steps',type=int,default=600);a=p.parse_args()
    if a.steps<1:raise ValueError('positive steps required')
    started=time.perf_counter();source=json.loads(a.trace.read_text());recipe,manifest=select_ruleset(source.get('recipe',source),a.ruleset)
    records=[];cases={i:input_cases(r) for i,r in enumerate(recipe['rules'])}
    base=samples(recipe,1,0,records,ordered=True,eq_targets=True,input_cases=cases)
    chain,coverage=chains(recipe,records,ordered=True,eq_targets=True,finite_boundary=True)
    width=max(len(r['slots']) for r in recipe['rules'])
    mx.random.seed(117);model=CompletionReadout(base['x'].shape[-1],base['relations'].shape[-1],width);model.load_weights(str(a.weights))
    from mlx.utils import tree_flatten
    frozen={k:np.array(v).copy() for k,v in tree_flatten(model.cell.parameters()) if k.startswith(('relation.','match_relation.'))}
    device=lambda d:{k:mx.array(v) for k,v in d.items()}
    db,dc=device(base),device(chain)
    def evaluate():
        outputs=[];accepted=[]
        for start in range(0,len(chain['valid']),128):
            c={k:v[start:start+128] for k,v in dc.items()};parent={k:v[c['parent']] for k,v in db.items()}
            first,second,t=rollout(model.cell,parent,c);scores=model.eq(t,c['request']);mx.eval(first,second,scores)
            outputs.append(np.array(scores));accepted.append((np.array(first)>=0)&(np.array(second)>=0))
        scores=np.concatenate(outputs);accepted=np.concatenate(accepted);positive=chain['valid']
        return dict(eq=metrics(scores[positive],chain['eq_target'][positive],chain['eq_mask'][positive],width),
                    matching_errors=int(np.sum(accepted!=positive)),
                    by_consumer={str(r):metrics(scores[positive&(chain['consumer']==r)],chain['eq_target'][positive&(chain['consumer']==r)],chain['eq_mask'][positive&(chain['consumer']==r)],width) for r in range(len(recipe['rules']))})
    before=evaluate();print(json.dumps(dict(before=before)),flush=True)
    gradient=nn.value_and_grad(model,objective);optimizer=optim.Adam(learning_rate=2e-4);rng=np.random.default_rng(418)
    for step in range(a.steps):
        ci=mx.array(rng.integers(len(chain['valid']),size=128));bi=mx.array(rng.integers(len(base['valid']),size=64))
        c={k:v[ci] for k,v in dc.items()};b={k:v[bi] for k,v in db.items()};parent={k:v[c['parent']] for k,v in db.items()}
        loss,g=gradient(model,b,parent,c);optimizer.update(model,g);mx.eval(loss,model.parameters(),optimizer.state)
        if step%100==0:print(json.dumps(dict(step=step,loss=float(loss))),flush=True)
    after=evaluate()
    current=dict(tree_flatten(model.cell.parameters()))
    if not frozen or not all(np.array_equal(v,np.array(current[k])) for k,v in frozen.items()):
        raise AssertionError('interface predicate weights changed or were not identified')
    model.save_weights(str(a.output.with_suffix('.safetensors')))
    model.cell.save_weights(str(a.output.with_suffix('.transition.safetensors')))
    model.eq.save_weights(str(a.output.with_suffix('.eq.safetensors')))
    result=dict(scope='standalone GPU fitting of bounded synthetic two-step domain; no runtime commits or generalization claim',
                stage_manifest=manifest,coverage=coverage,before=before,after=after,steps=a.steps,
                source_samples=len(base['valid']),backpropagation=True,generated_sources=True,promoted_as_default=False,
                interface_head_unchanged=True,
                recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),
                parent_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),
                weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest(),wall_seconds=time.perf_counter()-started)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(after=after)),flush=True)


if __name__=='__main__':main()
