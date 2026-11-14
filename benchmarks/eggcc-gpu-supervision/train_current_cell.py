"""Fit ephemeral current-Cell features; no recurrent latent inputs or targets."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_ordered_relations import ordered_model
from neural_eq_readout import EqReadout, masked_loss, metrics


class CurrentCellModel(nn.Module):
    def __init__(self, fields, relations, slots):
        super().__init__()
        self.field_capacity = fields // 128
        self.cell = ordered_model(fields, relations, True)
        self.eq = EqReadout(slots)

    def current_candidate_batch(self, state, frames, plan, xp):
        from device_current_cell_inputs import current_candidates
        return current_candidates(state, frames, plan, self.cell.encode,
                                  xp.array(True), xp.array(True), xp,
                                  field_capacity=self.field_capacity)

    def transition(self, *args):
        return self.cell.transition(*args)

    def __call__(self, batch):
        # Explicit allowlist: CPU labels, provenance and history never enter.
        inputs = self.cell.encode(batch['x']) + batch['source_tags']
        logits, temporary = self.cell.transition(inputs, batch['edges'],
            batch['mask'], batch['request'], batch['relations'])
        return logits, self.eq(temporary, batch['request'])


def loss(model, batch):
    logits, scores = model(batch)
    return (nn.losses.binary_cross_entropy(logits, batch['valid'], reduction='mean') +
            masked_loss(scores, batch['eq_target'], batch['eq_mask']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('dataset', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--steps', type=int, default=600)
    a = p.parse_args()
    if a.steps < 1: raise ValueError('positive steps required')
    manifest = json.loads(a.dataset.with_suffix('.json').read_text())
    digest = hashlib.sha256(a.dataset.read_bytes()).hexdigest()
    if not manifest.get('current_state_inputs') or manifest['dataset_sha256'] != digest:
        raise ValueError('verified current-state dataset required')
    raw = dict(np.load(a.dataset, allow_pickle=False))
    slots = (1 + math.isqrt(1+8*raw['eq_target'].shape[1]))//2
    mx.random.seed(2026)
    model = CurrentCellModel(raw['x'].shape[-1], raw['relations'].shape[-1], slots)
    data = {k:mx.array(v) for k,v in raw.items()}
    def evaluate():
        logits=[]; scores=[]
        for start in range(0,len(raw['valid']),64):
            l,s=model({k:v[start:start+64] for k,v in data.items()})
            mx.eval(l,s);logits.append(np.array(l));scores.append(np.array(s))
        pos=raw['valid']>0
        return dict(matching_errors=int(np.sum((np.concatenate(logits)>=0)!=pos)),
            eq=metrics(np.concatenate(scores)[pos],raw['eq_target'][pos],raw['eq_mask'][pos],slots))
    before=evaluate(); gradient=nn.value_and_grad(model,loss)
    optimizer=optim.Adam(learning_rate=3e-4);rng=np.random.default_rng(2026)
    for step in range(a.steps):
        ids=mx.array(rng.integers(len(raw['valid']),size=64))
        value,g=gradient(model,{k:v[ids] for k,v in data.items()})
        optimizer.update(model,g);mx.eval(value,model.parameters(),optimizer.state)
        if step%100==0:print(json.dumps(dict(step=step,loss=float(value))),flush=True)
    after=evaluate();model.save_weights(str(a.output.with_suffix('.safetensors')))
    result=dict(scope='training-domain fit of synthetic current-Cell inputs; not a Run audit',
                dataset_sha256=digest,recipe_sha256=manifest['recipe_sha256'],steps=a.steps,
                before=before,after=after,recurrent_latent_inputs=False,backpropagation=True,
                promoted_as_default=False,input_width=int(raw['x'].shape[-1]))
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__ == '__main__': main()
