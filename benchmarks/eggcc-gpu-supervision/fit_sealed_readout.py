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
    p.add_argument('--steps',type=int,default=300);p.add_argument('--anchors',type=Path);a=p.parse_args()
    if a.steps<1:raise ValueError('positive training budget required')
    manifest=json.loads(a.capture.with_suffix('.json').read_text())
    fingerprint=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if fingerprint(a.capture)!=manifest['sealed_capture']['sha256']:raise ValueError('capture mismatch')
    if fingerprint(a.weights)!=manifest['readout_weights_sha256']:raise ValueError('readout mismatch')
    data=dict(np.load(a.capture,allow_pickle=False));width=(1+math.isqrt(1+8*data['eq_target'].shape[1]))//2
    if width*(width-1)//2!=data['eq_target'].shape[1]:raise ValueError('invalid Eq layout')
    head=EqReadout(width);head.load_weights(str(a.weights));device={k:mx.array(v) for k,v in data.items()}
    anchors=None;da=None
    if a.anchors:
        am=json.loads(a.anchors.with_suffix('.json').read_text())
        if am['capture']['sha256']!=fingerprint(a.anchors):raise ValueError('anchor capture mismatch')
        if am['hashes']['transition']!=manifest['weights_sha256'] or am['recipe_sha256']!=manifest['recipe_sha256']:raise ValueError('incompatible anchor domain/model')
        anchors=dict(np.load(a.anchors,allow_pickle=False));da={k:mx.array(v) for k,v in anchors.items()}
        for k in ('token','request','eq_target','eq_mask'):
            if anchors[k].shape[1:]!=data[k].shape[1:]:raise ValueError('incompatible anchor layout')
    def evaluate(d,gpu):
        out=head(gpu['token'],gpu['request']);mx.eval(out)
        return metrics(np.array(out),d['eq_target'],d['eq_mask'],width)
    before=evaluate(data,device);anchor_before=evaluate(anchors,da) if anchors is not None else None
    def loss_fn(m,b,c):
        loss=masked_loss(m(b['token'],b['request']),b['eq_target'],b['eq_mask'])
        if c is not None:loss=loss+masked_loss(m(c['token'],c['request']),c['eq_target'],c['eq_mask'])
        return loss
    gradient=nn.value_and_grad(head,loss_fn)
    optimizer=optim.Adam(learning_rate=1e-4);rng=np.random.default_rng(204)
    for step in range(a.steps):
        indices=mx.array(rng.integers(len(data['token']),size=64));batch={k:v[indices] for k,v in device.items()}
        anchor_batch=None
        if da is not None:
            ai=mx.array(rng.integers(len(anchors['token']),size=64));anchor_batch={k:v[ai] for k,v in da.items()}
        loss,g=gradient(head,batch,anchor_batch);optimizer.update(head,g);mx.eval(loss,head.parameters(),optimizer.state)
    after=evaluate(data,device);anchor_after=evaluate(anchors,da) if anchors is not None else None
    head.save_weights(str(a.output.with_suffix('.safetensors')))
    result=dict(scope='training-set fitting of detached synthetic sealed Run tokens; not runtime acceptance',before=before,after=after,
                steps=a.steps,transition_unchanged=True,transition_sha256=manifest['weights_sha256'],recipe_sha256=manifest['recipe_sha256'],
                capture_sha256=fingerprint(a.capture),parent_sha256=fingerprint(a.weights),weights_sha256=fingerprint(a.output.with_suffix('.safetensors')),promoted_as_default=False,
                anchor_before=anchor_before,anchor_after=anchor_after,anchor_sha256=fingerprint(a.anchors) if a.anchors else None)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
