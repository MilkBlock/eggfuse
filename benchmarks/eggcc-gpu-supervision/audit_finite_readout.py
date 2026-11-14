"""Compare Eq heads on the same generated finite-domain tokens, no training."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from device_stage_models import select_ruleset
from finite_entry_domain import input_cases
from neural_cell_samples import samples
from neural_cell_chains import chains
from neural_ordered_relations import ordered_model
from neural_eq_readout import EqReadout,metrics
from train_neural_cell_chains import rollout


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('transition',type=Path)
    p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--capture',type=Path);a=p.parse_args()
    source=json.loads(a.trace.read_text());recipe,_=select_ruleset(source.get('recipe',source),'canon')
    records=[];base=samples(recipe,1,0,records,ordered=True,eq_targets=True,input_cases={i:input_cases(r) for i,r in enumerate(recipe['rules'])})
    chain,coverage=chains(recipe,records,ordered=True,eq_targets=True,finite_boundary=True)
    width=max(len(r['slots']) for r in recipe['rules']);model=ordered_model(base['x'].shape[-1],base['relations'].shape[-1],True)
    model.load_weights(str(a.transition));heads=[EqReadout(width),EqReadout(width)]
    for head,path in zip(heads,(a.before,a.after)):head.load_weights(str(path))
    db={k:mx.array(v) for k,v in base.items()};outputs=[[],[]];positive=np.flatnonzero(chain['valid']);captured=[]
    for start in range(0,len(positive),128):
        rows=positive[start:start+128];c={k:mx.array(v[rows]) for k,v in chain.items()};parent={k:v[c['parent']] for k,v in db.items()}
        _,_,tokens=rollout(model,parent,c)
        for head,out in zip(heads,outputs):
            scores=head(tokens,c['request']);mx.eval(scores);out.append(np.array(scores))
        if a.capture:captured.append(np.array(tokens))
    results=[metrics(np.concatenate(out),chain['eq_target'][positive],chain['eq_mask'][positive],width) for out in outputs]
    result=dict(scope='generated-token finite training-domain readout regression; not runtime or held-out generalization',
                coverage=coverage,before=results[0],after=results[1],
                hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in [('transition',a.transition),('before',a.before),('after',a.after)]})
    result['recipe_sha256']=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    if a.capture:
        np.savez_compressed(a.capture,token=np.concatenate(captured),**{k:chain[k][positive] for k in ('request','eq_target','eq_mask')})
        result['capture']=dict(samples=len(positive),sha256=hashlib.sha256(a.capture.read_bytes()).hexdigest())
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
