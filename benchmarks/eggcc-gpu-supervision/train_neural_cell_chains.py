"""Backpropagate through generated Cell states in real rule-derived two-step tuples."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_cell_samples import samples
from neural_cell_chains import chains
from neural_cell_transition import CellTransition,loss


def rollout(model,parent,chain,teacher=False):
    first,token=model(parent['x'],parent['edges'],parent['mask'],parent['request'],**({'relations':parent['relations']} if 'relations' in parent else {}))
    incoming=chain['tokens'] if teacher else mx.where(chain['replace'][...,None],token[:,None,:],chain['tokens'])
    second,target=model.transition(incoming,chain['edges'],chain['mask'],chain['request'],**({'relations':chain['relations']} if 'relations' in chain else {}))
    return first,second,target


def chain_loss(model,batch,parent,chain):
    first,second,out=rollout(model,parent,chain)
    matching=nn.losses.binary_cross_entropy(first,mx.ones_like(first),reduction='mean')+nn.losses.binary_cross_entropy(second,chain['valid'].astype(mx.float32),reduction='mean')
    error=mx.mean((out-chain['target'])**2,axis=1)
    return loss(model,batch)+matching+mx.sum(error*chain['valid'])/mx.maximum(mx.sum(chain['valid']),1)


def build(recipe,count,seed,ordered=False):
    records=[];base=samples(recipe,count,seed,records,ordered=ordered);data,coverage=chains(recipe,records,ordered=ordered)
    return base,data,coverage


def fingerprints(base,data):
    result=[]
    for i,parent in enumerate(data['parent']):
        parts=[base[k][parent].tobytes() for k in ('x','edges','mask','request')]
        # Ground-truth generated token is not part of the recurrent input.
        fixed=np.where(data['replace'][i,:,None],0,data['tokens'][i])
        parts += [fixed.tobytes()]+[data[k][i].tobytes() for k in ('edges','mask','replace','request')]
        result.append(hashlib.sha256(b''.join(parts)).hexdigest())
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('recipe',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path);p.add_argument('--steps',type=int,default=400);a=p.parse_args()
    if a.steps<1:raise ValueError('positive steps required')
    r=json.loads(a.recipe.read_text());r=r.get('recipe',r);ids=[i for i,v in enumerate(r['rules']) if v['metadata']['source_set']=='context'];recipe=dict(r,rules=[r['rules'][i] for i in ids]);started=time.perf_counter()
    base,chain,coverage=build(recipe,8,23001);test,tc,test_coverage=build(recipe,4,93003)
    seen=set(fingerprints(base,chain));overlap=np.array([v in seen for v in fingerprints(test,tc)])
    device=lambda d:{k:mx.array(v) for k,v in d.items()}
    db,dc,dt,de=map(device,(base,chain,test,tc));model=CellTransition(base['x'].shape[-1]);model.load_weights(str(a.weights));optimizer=optim.Adam(learning_rate=3e-4)
    def evaluate():
        parent={k:v[de['parent']] for k,v in dt.items()};a,b,t=rollout(model,parent,de);_,teacher,truth=rollout(model,parent,de,True);mx.eval(a,b,t,teacher,truth)
        accepted=(np.array(a)>=0)&(np.array(b)>=0);positive=tc['valid'];err=np.mean((np.array(t)-tc['target'])**2,axis=1)
        return dict(chains=len(accepted),both_steps_accepted=int(accepted.sum()),second_rejected=int((np.array(b)<0).sum()),first_rejected=int((np.array(a)<0).sum()),matching_correct=int((accepted==positive).sum()),false_positive=int((accepted&~positive).sum()),false_negative=int((~accepted&positive).sum()),token_mse=float(err[positive].mean()),teacher_token_mse=float(np.mean((np.array(truth)[positive]-tc['target'][positive])**2)),unseen_features=int((~overlap).sum()),unseen_both_steps_accepted=int(accepted[~overlap].sum()),unseen_matching_correct=int((accepted[~overlap]==positive[~overlap]).sum()),unseen_token_mse=float(err[~overlap&positive].mean()) if (~overlap&positive).any() else None)
    before=evaluate();print(json.dumps(dict(before=before,coverage=coverage)),flush=True)
    grad=nn.value_and_grad(model,chain_loss);rng=np.random.default_rng(47)
    for step in range(a.steps):
        ci=mx.array(rng.integers(0,len(chain['parent']),64));bi=mx.array(rng.integers(0,len(base['valid']),128));c={k:v[ci] for k,v in dc.items()};b={k:v[bi] for k,v in db.items()};parent={k:v[c['parent']] for k,v in db.items()}
        value,g=grad(model,b,parent,c);optimizer.update(model,g);mx.eval(value,model.parameters(),optimizer.state)
        if step%100==0:print(json.dumps(dict(step=step,loss=float(value))),flush=True)
    after=evaluate();model.save_weights(str(a.output.with_suffix('.safetensors')))
    result=dict(recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),scope='GPU two-step generated-token training on synthetic effect-backed tuples; candidate wiring is supplied, not runtime enumeration',backpropagation=True,source_rules=ids,coverage=coverage,test_coverage=test_coverage,evaluation_training_feature_overlap=int(overlap.sum()),before=before,after=after,steps=a.steps,wall_seconds=time.perf_counter()-started,weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest(),parent_weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),limitations=['Second-step negatives are independently generated incompatible boundary facts; not every hard-negative mode','Acceptance means model logits, not exact semantic acceptance','Token MSE is not a proof of correct discrete completion','No runtime ownership transfer or complete ruleset saturation is established','Additional boundary facts are synthetic and verified not to change producer identities'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(after))
if __name__=='__main__':main()
