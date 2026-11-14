"""Train all selected context templates from synthetic candidates with gradients."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_cell_samples import samples
from neural_cell_transition import CellTransition,loss


def fingerprints(data):
    return [hashlib.sha256(b''.join(data[k][i].tobytes() for k in ('x','edges','mask','request'))).hexdigest() for i in range(len(data['valid']))]


def main():
    p=argparse.ArgumentParser();p.add_argument('recipe',type=Path);p.add_argument('output',type=Path);p.add_argument('--ruleset',default='context');p.add_argument('--samples-per-rule',type=int,default=128);p.add_argument('--steps',type=int,default=400);a=p.parse_args()
    if a.samples_per_rule<2 or a.steps<1:raise ValueError('positive steps and at least two samples per rule required')
    raw=json.loads(a.recipe.read_text());source=raw.get('recipe',raw);ids=[i for i,r in enumerate(source['rules']) if r['metadata']['source_set']==a.ruleset]
    if not ids:raise ValueError('empty ruleset')
    recipe=dict(source,rules=[source['rules'][i] for i in ids]);started=time.perf_counter()
    train=samples(recipe,a.samples_per_rule,12001);test=samples(recipe,32,92003)
    training_fingerprints=set(fingerprints(train))
    overlap=np.array([key in training_fingerprints for key in fingerprints(test)])
    train={k:mx.array(v) for k,v in train.items()};mx.random.seed(33);model=CellTransition(train['x'].shape[-1]);optimizer=optim.Adam(learning_rate=1e-3)
    grad=nn.value_and_grad(model,loss);rng=np.random.default_rng(44);history=[]
    # The forward pass has no input-dependent Python branch; training drives batches.
    for step in range(a.steps):
        ix=mx.array(rng.integers(0,len(train['valid']),128));batch={k:v[ix] for k,v in train.items()}
        value,g=grad(model,batch);optimizer.update(model,g);mx.eval(model.parameters(),optimizer.state,value)
        if step%100==0:history.append(dict(step=step,loss=float(value)));print(history[-1],flush=True)
    data={k:mx.array(v) for k,v in test.items()};logits,tokens=model(data['x'],data['edges'],data['mask'],data['request']);mx.eval(logits,tokens)
    pred=np.array(logits)>=0;token=np.array(tokens);groups=[]
    for local,rid in enumerate(ids):
        sel=test['rule']==local;pos=sel&(test['valid']>0);novel=sel&~overlap
        groups.append(dict(rule=rid,samples=int(sel.sum()),matching_correct=int((pred[sel]==test['valid'][sel]).sum()),positive=int(pos.sum()),token_mse=float(np.mean((token[pos]-test['target'][pos])**2)) if pos.any() else None,unseen_features=int(novel.sum()),unseen_matching_correct=int((pred[novel]==test['valid'][novel]).sum())))
    a.output.parent.mkdir(parents=True,exist_ok=True);model.save_weights(str(a.output.with_suffix('.safetensors')))
    report=dict(scope='standalone GPU learned candidate matching and immediate-effect token prediction; not runtime candidate enumeration, recurrent rollout or ownership acceptance',backpropagation=True,synthetic_only_training=True,source_rule_ids=ids,steps=a.steps,training_samples=len(train['valid']),evaluation_samples=len(test['valid']),evaluation_training_feature_overlap=int(overlap.sum()),matching_correct=int((pred==test['valid']).sum()),false_positive=int((pred&(test['valid']==0)).sum()),false_negative=int((~pred&(test['valid']>0)).sum()),groups=groups,history=history,wall_seconds=time.perf_counter()-started,recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest(),limitations=['Negatives are corrupted candidate bindings, not a full missed-match audit','Output targets are immediate local effects, not saturated family states','Exact typed connectivity is supplied alongside floating interface features','No ownership classifier or transfer is trained yet','Synthetic feature overlap is reported; aggregate accuracy is not unseen-structure generalization'])
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('training_samples','evaluation_samples','matching_correct','false_positive','false_negative','evaluation_training_feature_overlap','wall_seconds')}))
if __name__=='__main__':main()
