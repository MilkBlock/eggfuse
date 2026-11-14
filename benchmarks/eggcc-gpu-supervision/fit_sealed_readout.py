"""Fit frozen synthetic Run token readout; no generalization claim.

Only Eq readout weights change. Full Run and recurrent execution must be
rechecked; fitting detached captured inputs alone cannot establish correctness.
"""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_eq_readout import EqReadout,masked_loss,metrics


def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--steps',type=int,default=300);a=p.parse_args()
    if a.steps<1:raise ValueError('positive training budget required')
    manifest=json.loads(a.capture.with_suffix('.json').read_text())
    fingerprint=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if fingerprint(a.capture)!=manifest['sealed_capture']['sha256']:raise ValueError('capture mismatch')
    if fingerprint(a.weights)!=manifest['readout_weights_sha256']:raise ValueError('readout mismatch')
    data=dict(np.load(a.capture,allow_pickle=False));width=(1+math.isqrt(1+8*data['eq_target'].shape[1]))//2
    if width*(width-1)//2!=data['eq_target'].shape[1]:raise ValueError('invalid Eq layout')
    head=EqReadout(width);head.load_weights(str(a.weights));device={k:mx.array(v) for k,v in data.items()}
    def evaluate():
        out=head(device['token'],device['request']);mx.eval(out)
        return metrics(np.array(out),data['eq_target'],data['eq_mask'],width)
    before=evaluate();gradient=nn.value_and_grad(head,lambda m,b:masked_loss(m(b['token'],b['request']),b['eq_target'],b['eq_mask']))
    optimizer=optim.Adam(learning_rate=1e-4);rng=np.random.default_rng(204)
    for step in range(a.steps):
        indices=mx.array(rng.integers(len(data['token']),size=64));batch={k:v[indices] for k,v in device.items()}
        loss,g=gradient(head,batch);optimizer.update(head,g);mx.eval(loss,head.parameters(),optimizer.state)
    after=evaluate();head.save_weights(str(a.output.with_suffix('.safetensors')))
    result=dict(scope='training-set fitting of detached synthetic sealed Run tokens; not runtime acceptance',before=before,after=after,
                steps=a.steps,transition_unchanged=True,transition_sha256=manifest['weights_sha256'],recipe_sha256=manifest['recipe_sha256'],
                capture_sha256=fingerprint(a.capture),parent_sha256=fingerprint(a.weights),weights_sha256=fingerprint(a.output.with_suffix('.safetensors')),promoted_as_default=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
