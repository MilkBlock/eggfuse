"""Calibrate Eq readout on generated cumulative tokens, keeping Cell weights fixed.

Uses synthetic post-run supervision only. Detached inputs do not demonstrate
recurrent execution correctness; re-run the cumulative GPU audit afterward.
"""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from neural_eq_readout import EqReadout,metrics,masked_loss
from neural_ordered_relations import ordered_model
from neural_third_step import replay


def fingerprints(data):
    return [hashlib.sha256(data['token'][i].tobytes()+data['request'][i].tobytes()).digest() for i in range(len(data['token']))]


def main():
    p=argparse.ArgumentParser();p.add_argument('train',type=Path);p.add_argument('test',type=Path)
    p.add_argument('weights',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--anchors',type=Path,required=True);p.add_argument('--transition',type=Path,required=True)
    p.add_argument('--steps',type=int,default=600);a=p.parse_args()
    if a.steps<1:raise ValueError('positive steps required')
    manifests=[json.loads(path.with_suffix('.json').read_text()) for path in (a.train,a.test)]
    transition_hash=hashlib.sha256(a.transition.read_bytes()).hexdigest()
    readout_hash=hashlib.sha256(a.weights.read_bytes()).hexdigest()
    for path,manifest in zip((a.train,a.test),manifests):
        if manifest['capture']['sha256']!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('capture hash mismatch')
        if manifest['weights_sha256']!=transition_hash or manifest['readout_weights_sha256']!=readout_hash:raise ValueError('capture model mismatch')
    anchor_manifest=json.loads(a.anchors.with_suffix('.json').read_text())
    if len({m['recipe_sha256'] for m in manifests+[anchor_manifest]})!=1:raise ValueError('mixed stage recipes')
    train=dict(np.load(a.train,allow_pickle=False));test=dict(np.load(a.test,allow_pickle=False))
    width=int((1+math.isqrt(1+8*train['eq_target'].shape[1]))//2)
    if width*(width-1)//2!=train['eq_target'].shape[1]:raise ValueError('invalid pair layout')
    anchor=dict(np.load(a.anchors,allow_pickle=False));positive=np.flatnonzero(anchor['valid']>0)
    cell=ordered_model(anchor['p_x'].shape[-1],anchor['relations'].shape[-1],True)
    cell.load_weights(str(a.transition));tokens=[]
    for start in range(0,len(positive),128):
        rows=positive[start:start+128];batch={k:mx.array(v[rows]) for k,v in anchor.items()}
        _,t=replay(cell,batch);mx.eval(t);tokens.append(np.array(t))
    anchors=dict(token=np.concatenate(tokens),request=anchor['request'][positive],
                 eq_target=anchor['eq_target'][positive],eq_mask=anchor['eq_mask'][positive])
    head=EqReadout(width);head.load_weights(str(a.weights))
    device=lambda d:{k:mx.array(d[k]) for k in ('token','request','eq_target','eq_mask')}
    seen=set(fingerprints(train));novel=np.array([f not in seen for f in fingerprints(test)])
    def evaluate(data,selection=None):
        d=data if selection is None else {k:v[selection] for k,v in data.items()}
        outputs=[]
        for start in range(0,len(d['token']),128):
            scores=head(mx.array(d['token'][start:start+128]),mx.array(d['request'][start:start+128]));mx.eval(scores)
            outputs.append(np.array(scores))
        scores=np.concatenate(outputs) if outputs else np.zeros((0,width*(width-1)//2),np.float32)
        return metrics(scores,d['eq_target'],d['eq_mask'],width)
    def report():return dict(train=evaluate(train),test=evaluate(test),unseen=evaluate(test,novel),anchors=evaluate(anchors))
    before=report();print(json.dumps(dict(before=before)),flush=True)
    dt,da=device(train),device(anchors);rng=np.random.default_rng(9127)
    def loss(m,b,c):return masked_loss(m(b['token'],b['request']),b['eq_target'],b['eq_mask'])+.5*masked_loss(m(c['token'],c['request']),c['eq_target'],c['eq_mask'])
    grad=nn.value_and_grad(head,loss);optimizer=optim.Adam(learning_rate=2e-4)
    for step in range(a.steps):
        ti=mx.array(rng.integers(len(train['token']),size=64));ai=mx.array(rng.integers(len(anchors['token']),size=64))
        value,g=grad(head,{k:v[ti] for k,v in dt.items()},{k:v[ai] for k,v in da.items()})
        optimizer.update(head,g);mx.eval(value,head.parameters(),optimizer.state)
        if step%100==0:print(json.dumps(dict(step=step,loss=float(value))),flush=True)
    head.save_weights(str(a.output.with_suffix('.safetensors')))
    result=dict(scope='Eq-only calibration on detached synthetic cumulative tokens; not runtime verification',
                before=before,after=report(),steps=a.steps,transition_unchanged=True,
                train_samples=len(train['token']),test_samples=len(test['token']),test_input_overlap=int((~novel).sum()),
                inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.train,a.test,a.weights,a.anchors,a.transition)},
                weights_sha256=hashlib.sha256(a.output.with_suffix('.safetensors').read_bytes()).hexdigest())
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['after']))


if __name__=='__main__':main()
