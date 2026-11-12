"""Read-only audit of the finite latent-state study; no acceptance widening."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks/cell-real-state'))
import study


def gradient_check():
    rng = np.random.default_rng(110)
    batch, dim, events, hidden = 3, 4, 2, 5
    shapes = [(dim+events, hidden), (hidden,), (dim+events+hidden, dim), (dim,)]
    params = [rng.normal(size=shape)*.1 for shape in shapes]
    initial = rng.normal(size=(batch, dim))
    inputs = rng.normal(size=(3, batch, events))
    targets = rng.normal(size=(3, batch, dim))
    dw = rng.normal(size=(dim, 6))*.1
    db = rng.normal(size=6)*.1
    bits = rng.integers(0, 2, size=(3, batch, 6))

    def run(derivative=False):
        a,b,w,bias=params
        current=initial.copy(); tape=[]; loss=0
        for step in range(3):
            x=np.concatenate([current,inputs[step]],axis=1)
            t=np.tanh(x@a+b); feature=np.concatenate([x,t],axis=1)
            current=current+feature@w+bias
            logits=4*(current@dw+db-.5)
            probability=1/(1+np.exp(-logits))
            loss += np.mean((current-targets[step])**2)/3
            loss += .1*np.mean(np.logaddexp(0,logits)-bits[step]*logits)/3
            g=2*(current-targets[step])/(batch*dim*3)
            g+=.1*4*((probability-bits[step])@dw.T)/(batch*6*3)
            tape.append((x,t,feature,g))
        if not derivative:return loss
        grads=[np.zeros_like(p) for p in params];carry=np.zeros_like(current)
        for x,t,feature,local in reversed(tape):
            g=carry+local
            grads[2]+=feature.T@g;grads[3]+=g.sum(0)
            gf=g@w.T;gt=gf[:,dim+events:]*(1-t*t)
            grads[0]+=x.T@gt;grads[1]+=gt.sum(0)
            carry=g+gf[:,:dim]+(gt@a.T)[:,:dim]
        return grads

    analytical=run(True); errors=[]
    for p,g in zip(params,analytical):
        for ix in np.ndindex(p.shape):
            old=p[ix];eps=1e-6
            p[ix]=old+eps;plus=run()
            p[ix]=old-eps;minus=run()
            p[ix]=old
            errors.append(abs((plus-minus)/(2*eps)-g[ix]))
    assert max(errors)<1e-7
    return dict(checked_parameters=len(errors),maximum_absolute_error=max(errors),
                scope='float64 finite differences of the copied BPTT equations; excludes FP16 quantization and optimizer quality')


def main():
    states,facts,targets,train,valid,test=study.dataset()
    index=np.arange(len(states));records=[]
    for action in range(17):
        selected=train & train[targets[:,action]]
        changed=targets[:,action]!=index
        records.append(dict(action=action,training_edges=int(selected.sum()),
                            training_changes=int((selected&changed).sum()),
                            testing_changes=int((test&changed).sum()),
                            testing_unseen_targets=int((test&~train[targets[:,action]]).sum()),
                            distinct_training_targets=len(set(targets[selected,action]))))
    counts=np.bincount(targets.ravel(),minlength=len(states))
    popular=[]
    for i in np.argsort(-counts)[:12]:
        popular.append(dict(index=int(i),flags=states[i][1],base_classes=len(set(states[i][0][:6])),
                            split='train' if train[i] else 'validation' if valid[i] else 'test',
                            incoming=int(counts[i])))
    feedback=0;rules=0
    for partition in study.partitions(6):
        baseline=study.close(partition,0)[0];full=study.close(partition,3)[0]
        feedback+=baseline[:6]!=full[:6];rules+=baseline!=full
    report=dict(source_sha256=hashlib.sha256(Path(study.__file__).read_bytes()).hexdigest(),
                gradient=gradient_check(),actions=records,popular_targets=popular,
                excluded_train_to_held_edges=int((train[:,None]&~train[targets]).sum()),
                base_partitions=203,partitions_with_rule_effect=rules,partitions_with_boundary_feedback=feedback)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
