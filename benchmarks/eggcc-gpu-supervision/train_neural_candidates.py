"""Fine-tune pooled matching while retaining generated-token chain objectives."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_candidate_training import pooled_candidates
from neural_cell_transition import CellTransition
from train_neural_cell_chains import build, chain_loss, rollout
from train_neural_cell_transition import fingerprints


def scores(model, data):
    predictions = []
    for start in range(0, len(data['valid']), 256):
        b = {k:mx.array(v[start:start+256]) for k,v in data.items()}
        logits, _ = model(b['x'], b['edges'], b['mask'], b['request'])
        predictions.append(np.array(logits) >= 0)
    p = np.concatenate(predictions); truth = data['valid'] > 0
    return dict(samples=len(p), correct=int((p == truth).sum()), false_positive=int((p & ~truth).sum()), false_negative=int((~p & truth).sum()))


def objective(model, batch, parent, chain, pool):
    logits, _ = model(pool['x'], pool['edges'], pool['mask'], pool['request'])
    return chain_loss(model, batch, parent, chain) + nn.losses.binary_cross_entropy(logits, pool['valid'], reduction='mean')


def main():
    p = argparse.ArgumentParser(); p.add_argument('trace', type=Path); p.add_argument('weights', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--steps', type=int, default=400); p.add_argument('--shared-fraction', type=float, default=.35); a = p.parse_args()
    if a.steps < 1: raise ValueError('positive steps required')
    source = json.loads(a.trace.read_text()); source = source.get('recipe', source)
    source_ids = [i for i,r in enumerate(source['rules']) if r['metadata']['source_set']=='context']
    recipe = dict(source, rules=[source['rules'][i] for i in source_ids]); started=time.perf_counter()
    train, coverage = pooled_candidates(recipe, 41001, shared_fraction=a.shared_fraction)
    test, test_coverage = pooled_candidates(recipe, 97003, examples=8, per_class=64, shared_fraction=a.shared_fraction)
    seen = set(fingerprints(train)); unseen = np.array([k not in seen for k in fingerprints(test)]); overlap = int((~unseen).sum())
    print(json.dumps(dict(training=len(train['valid']), test=len(test['valid']), overlap=overlap)), flush=True)
    base, chain, _ = build(recipe, 8, 23001); tb, tc, _ = build(recipe, 4, 93003)
    device = lambda d:{k:mx.array(v) for k,v in d.items()}
    db, dc, dp = map(device, (base, chain, train))
    model=CellTransition(train['x'].shape[-1]); model.load_weights(str(a.weights))
    def evaluate():
        parent=device({k:v[tc['parent']] for k,v in tb.items()})
        first, second, token=rollout(model, parent, device(tc)); mx.eval(first, second, token)
        accepted=(np.array(first)>=0)&(np.array(second)>=0); positive=tc['valid']
        return dict(pool=scores(model,test), unseen_pool=scores(model,{k:v[unseen] for k,v in test.items()}) if unseen.any() else None, chain=dict(samples=len(accepted),false_positive=int((accepted&~positive).sum()),false_negative=int((~accepted&positive).sum()),token_mse=float(np.mean((np.array(token)[positive]-tc['target'][positive])**2))))
    before=evaluate(); print(json.dumps(dict(before=before)),flush=True)
    grad=nn.value_and_grad(model,objective); optimizer=optim.Adam(learning_rate=3e-4); rng=np.random.default_rng(51)
    for step in range(a.steps):
        bi=mx.array(rng.integers(len(base['valid']),size=128)); ci=mx.array(rng.integers(len(chain['valid']),size=64)); pi=mx.array(rng.integers(len(train['valid']),size=128))
        batch={k:v[bi] for k,v in db.items()}; c={k:v[ci] for k,v in dc.items()}; parent={k:v[c['parent']] for k,v in db.items()}; pool={k:v[pi] for k,v in dp.items()}
        value,g=grad(model,batch,parent,c,pool); optimizer.update(model,g); mx.eval(value,model.parameters(),optimizer.state)
        if step%100==0: print(json.dumps(dict(step=step,loss=float(value))),flush=True)
    after=evaluate(); model.save_weights(str(a.output.with_suffix('.safetensors')))
    report=dict(scope='standalone synthetic pooled matching and generated-token chain training; no graph commits or ownership execution',synthetic_only_training=True,shared_fraction=a.shared_fraction,source_rules=source_ids,training_coverage=coverage,test_coverage=test_coverage,evaluation_feature_overlap=overlap,before=before,after=after,steps=a.steps,wall_seconds=time.perf_counter()-started,parent_weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest(),promoted_as_default=False)
    a.output.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(after))


if __name__=='__main__': main()
