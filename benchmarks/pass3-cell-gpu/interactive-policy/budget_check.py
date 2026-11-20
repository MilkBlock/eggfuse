"""Compare frozen reply features at exactly the same feasible proposal count per source epoch."""
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
import torch
from corpus import Ports,read_ports,later_labels,neural_origin
from policy import Selector
from study import MODES,Native,Replay,metrics


def rank_ports(port,raw_blind,scores,bounds,pooled):
    e=port.events
    legal=np.stack([e[:,5]>=e[:,7],e[:,6]==e[:,8]],1)
    baseline=raw_blind[:,[0,2]]&legal
    result=np.zeros_like(baseline)
    for lo,hi in bounds:
        feasible=legal[lo:hi]
        logits=scores[lo:hi][:,[0,2]]
        if pooled:
            candidates=np.flatnonzero(feasible.ravel())
            # Stable ordering gives deterministic ties across identical keys.
            order=candidates[np.argsort(-logits.ravel()[candidates],kind='stable')]
            slots=int(baseline[lo:hi].sum())
            rr,cc=np.unravel_index(order[:slots],feasible.shape)
            result[lo+rr,cc]=True
        else:
            for c in (0,1):
                candidates=np.flatnonzero(feasible[:,c])
                order=candidates[np.argsort(-logits[candidates,c],kind='stable')]
                slots=int(baseline[lo:hi,c].sum())
                result[lo+order[:slots],c]=True
        assert result[lo:hi].sum()==baseline[lo:hi].sum()
        if not pooled:np.testing.assert_array_equal(result[lo:hi].sum(0),baseline[lo:hi].sum(0))
    prediction=np.stack([result[:,0]&(e[:,5]==e[:,7]),result[:,0]&(e[:,5]>e[:,7]),result[:,1]],1)
    raw=np.stack([result[:,0],e[:,5]>e[:,7],result[:,1]],1)
    return prediction,raw


@torch.inference_mode()
def main(a):
    torch.set_num_threads(1)
    saved=json.loads((a.weights/'results.json').read_bytes())
    vocab=set()
    for n in saved['train']:
        x=read_ports(a.families/n/'input',a.train_capture/n)
        vocab.update((int(e[2]),int(e[3])) for e in x.events)
    vocab={v:i+1 for i,v in enumerate(sorted(vocab))}
    records={}
    with tempfile.TemporaryDirectory() as tmp:
        native=Native(Path(tmp))
        for seed in (1703,1709):
            net=Selector(len(vocab));net.load_state_dict(torch.load(a.weights/f'policy-{seed}.pt',weights_only=True));net.eval()
            for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
                img=a.ref/f'release-input-{n}' if n in ('sum-bits','dot-product') else a.families/n/'input'
                cap=a.capture/n;ports=read_ports(img,cap);y,count,_=later_labels(cap,ports)
                neural=neural_origin(cap,a.online/f'{n}-{seed}-batch',ports)
                for cohort,ix in [('source',np.ones(len(y),bool)),('neural',neural)]:
                    sub=Ports(ports.events[ix],ports.branches,ports.optional)
                    replay=Replay(sub,vocab,'cpu')
                    outcomes={m:replay.run(net,m,native,return_scores=True) for m in MODES if m!='deferred'}
                    raw_blind=outcomes['blind'][1]
                    assert all(o[4].shape==raw_blind.shape for o in outcomes.values())
                    for pooled in (False,True):
                        preds={};data={}
                        for m,o in outcomes.items():
                            pred,raw=rank_ports(sub,raw_blind,o[4],replay.bounds,pooled)
                            preds[m]=pred;data[m]=metrics(y[ix],count[ix],pred,raw)
                            data[m]['changed_choice_ports_vs_blind']=int((preds['blind']!=pred).any(1).sum())
                        assert len({v['selected'] for v in data.values()})==1
                        records[f'{n}/{seed}/{cohort}/'+('pooled' if pooled else 'separate')]=data
    a.out.write_text(json.dumps(records,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('ref','families','train_capture','capture','online','weights','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
