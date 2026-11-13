"""No-backprop token rollout diagnostic on saved actual Run boundaries.
No graph decoding or teacher substitution occurs between predicted steps.
"""
import argparse, hashlib, importlib.util, json, time
from pathlib import Path
import numpy as np
import mlx.core as mx


def module(name, path):
    import sys
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m


def main():
    p=argparse.ArgumentParser();p.add_argument('--reference-dir',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    ds=module('dataset',a.reference_dir/'dataset.py');tr=module('train',a.reference_dir/'train.py')
    runtime=json.loads(a.runtime.read_text());corpus=json.loads(a.corpus.read_text())
    split={r['id']:r['split'] for r in corpus['records']}
    encoder=tr.Encoder();groups={'train':[],'validation':[],'test':[]};successors={};cases=[]
    for c in runtime['cases']:
        if c['id'] not in split:continue
        assert c['fixed_point']['status']=='pass'
        graphs=[c['initial']]+[b['graph'] for b in c['boundaries']]
        nodes=[ds.canonical(g)[0] for g in graphs]
        final=ds.canonical(c['final'])[0]
        assert nodes[-1]==final
        tokens=np.stack([encoder(n) for n in nodes]);keys=[ds.digest(n) for n in nodes]
        item=dict(id=c['id'],split=split[c['id']],tokens=tokens,keys=keys,final=keys[-1])
        groups[item['split']].append(item);cases.append(item)
        for i in range(len(keys)-1):
            key=(c['steps'][i]['ruleset'],keys[i]);successors.setdefault(key,set()).add(keys[i+1])
    train=groups['train'];valid=groups['validation'];test=groups['test']
    x=np.concatenate([c['tokens'][:-1] for c in train]);y=np.concatenate([c['tokens'][1:] for c in train])
    mean=x.mean(0);scale=np.maximum(x.std(0),.1)
    rng=np.random.default_rng(10291);projection=rng.normal(0,1/np.sqrt(x.shape[1]),(x.shape[1],256)).astype(np.float32)
    bias=rng.normal(0,.3,256).astype(np.float32)
    def phi(t):
        z=(t-mean)/scale
        return np.concatenate([z,np.tanh(z@projection+bias)],axis=1)
    # Learn a residual transform. There is no optimization through rollout.
    choices=[];models=[]
    for reg in (0.01,1.,100.):
        w,b=tr.fit(phi(x),y-x,reg)
        def step(t):return t+phi(t)@w+b
        v=np.stack([c['tokens'][0] for c in valid])
        for _ in range(8):v=step(v)
        target=np.stack([c['tokens'][-1] for c in valid])
        loss=float(np.mean(((v-target)/scale)**2));choices.append(dict(regularization=reg,validation_rollout8_mse=loss));models.append((w,b))
    selected=int(np.argmin([v['validation_rollout8_mse'] for v in choices]));w,b=models[selected]
    def step(t):return t+phi(t)@w+b
    # Training-only known completion catalog; diagnostic nearest-token decode at exit only.
    catalog={c['final']:c['tokens'][-1] for c in train};labels=list(catalog);centers=np.stack(list(catalog.values()))
    def measure(t):
        truth=np.stack([c['tokens'][-1] for c in test])
        distance=(((t[:,None,:]-centers[None,:,:])/scale)**2).mean(2)
        predicted=[labels[i] for i in distance.argmin(1)]
        return dict(scaled_final_mse=float(np.mean(((t-truth)/scale)**2)),nearest_known_completion_correct=sum(q==c['final'] for q,c in zip(predicted,test)),total=len(test))
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    gm,gs,gp,gq,gw,gb=map(mx.array,[mean,scale,projection,bias,w,b])
    def gpu_step(t):
        z=(t-gm)/gs
        return t+mx.concatenate([z,mx.tanh(z@gp+gq)],axis=1)@gw+gb
    def rollout8(t):
        for _ in range(8):t=gpu_step(t)
        return t
    gpu=mx.compile(rollout8)
    original=np.stack([c['tokens'][0] for c in test]);state=original.copy();rollouts={}
    for k in range(1,9):
        state=step(state)
        if k in (1,2,4,8):rollouts[str(k)]=measure(state)
    result_gpu=gpu(mx.array(original));mx.eval(result_gpu);host=np.array(result_gpu)
    assert np.isfinite(host).all()
    # Numerical proximity is reported rather than assuming exact equality.
    tx=np.concatenate([c['tokens'][:-1] for c in test]);ty=np.concatenate([c['tokens'][1:] for c in test])
    transition_keys={k for c in train for k in c['keys'][:-1]}
    unseen=np.array([k not in transition_keys for c in test for k in c['keys'][:-1]])
    np.testing.assert_allclose(host,state,rtol=1e-4,atol=3e-4)
    report=dict(scope='Standalone saved-boundary token prediction, not runtime takeover or semantic completion',
        provenance={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [a.runtime,a.corpus,a.reference_dir/'dataset.py',a.reference_dir/'train.py']},
        cases={k:len(v) for k,v in groups.items()},train_transitions=len(x),test_transitions=len(tx),
        conflicting_graph_and_ruleset_successors=sum(len(v)>1 for v in successors.values()),
        test_transition_states_seen_in_training=sum(k in transition_keys for c in test for k in c['keys'][:-1]),
        selection=choices,selected_regularization=choices[selected]['regularization'],
        teacher_input_one_step_scaled_mse=float(np.mean(((step(tx)-ty)/scale)**2)),
        unseen_state_one_step_scaled_mse=float(np.mean(((step(tx[unseen])-ty[unseen])/scale)**2)) if unseen.any() else None,
        unseen_state_transitions=int(unseen.sum()),
        persistence_one_step_scaled_mse=float(np.mean(((tx-ty)/scale)**2)),
        rollout=rollouts,gpu_rollout8=measure(host),cpu_gpu_max_abs_difference=float(np.max(np.abs(state-host))),
        exact_final_token_catalog_diagnostic=measure(np.stack([c['tokens'][-1] for c in test])),
        unseen_test_completions=sum(c['final'] not in catalog for c in test),
        token_width=x.shape[1],random_feature_width=256,backpropagation=False,
        intermediate_graph_decodes=0,intermediate_teacher_substitutions=0,
        limitations=['CPU recursive graph encoder; not live shared slots','Run transition model does not encode delta or watermark',
        'nearest completion label is diagnostic, not proof or executable result','CPU residual completion not implemented',
        'existing development split, not a fresh blind test','No runtime speedup claimed'])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
