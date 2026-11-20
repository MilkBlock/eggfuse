"""Full scheduled Pass 3. Each Run has two proposal/verification waves and one residual search."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from capture import execute, inputs, load_catalog, read, verify
from feedback import FeedbackActor, training_reply
from model import HIDDEN, ROWS, RANKS
from provenance import validate


def audit(folder, data, checkpoint, entries, mode, shuffle, exclude_closed=False):
    net = FeedbackActor()
    net.load_state_dict(torch.load(checkpoint/'actor.pt', weights_only=True))
    net.eval()
    with np.load(data/'training.npz') as z:
        features, truth, labels = [torch.from_numpy(z[k]) for k in ('features','positive','receipt')]
    with np.load(folder/'neural-output.npz') as z:
        raw, verdict, won = [z[k].copy() for k in ('raw','verdict','committed')]
    with np.load(folder/'output.npz') as z:
        counts = z['runs'][:,1]
    assert len(raw) == len(features) == len(counts)
    prev = torch.zeros(1, ROWS, HIDDEN+4)
    reply = torch.zeros(1, ROWS, 4, dtype=torch.long)
    largest = 0.
    remaining = []
    repeats = retry = stale_retry = 0
    total_discrete = 0
    for t in range(len(raw)):
        closed = torch.zeros_like(truth[t:t+1])
        for wave in range(2):
            slot = slice(wave*ROWS, (wave+1)*ROWS)
            _, prev = net.propose(features[t:t+1], prev, reply, wave, mode, shuffle, exclude_closed)
            device_token = torch.from_numpy(raw[t,slot])[None]
            total_discrete += int((prev[...,HIDDEN:]!=device_token[...,HIDDEN:]).any(-1).sum())
            largest = max(largest, float((prev[...,:HIDDEN]-device_token[...,:HIDDEN]).abs().max()))
            # Reconstruct verifier replies from independent capture, not from the online file.
            reply, closed = training_reply(prev, labels[t:t+1], closed)
            actual = torch.from_numpy(verdict[t,slot])[None]
            np.testing.assert_array_equal(reply[...,:3], actual[...,:3], err_msg=f'Run {t+1} wave {wave}')
            rejected = actual[...,0] == 2
            np.testing.assert_array_equal(reply[...,3][rejected], actual[...,3][rejected])
        remaining.append(int((truth[t:t+1] & ~closed).sum()))
        for status, leaf, anchor, _ in verdict[t,2:]:
            if status:
                prior = [v for v in verdict[t,:2] if v[0] and (v[1],v[2])==(leaf,anchor)]
                repeats += any(v[0] in (1,3) for v in prior)
                retry += any(v[0]==2 for v in prior)
                stale_retry += any(v[0]==2 and v[3]==-4 for v in prior)
    assert total_discrete == 0 and largest < .002, (total_discrete, largest)
    stats = read(folder/'run.json')
    credited = validate(folder,entries)
    assert credited == int(won.sum()) == stats['execution_roles']['rhs_inputs_from_recurrent_neural_proposals']
    waves = []
    for start in (0,2):
        code = verdict[:,start:start+2,0]
        waves.append(dict(raw=int((code!=0).sum()), abstained=int((code==0).sum()),
                          accepted=int((code==1).sum()), rejected=int((code==2).sum()),
                          duplicate=int((code==3).sum()), committed=won[:,start:start+2].sum(0).tolist()))
    return dict(runs=len(counts), rhs=int(counts.sum()), committed=credited,
                exact_residual=int(counts.sum())-credited, nonempty=int((counts>0).sum()),
                complete_nonempty=int(((counts>0)&(counts==won.sum(1))).sum()), waves=waves,
                wave2_reclaims=repeats, wave2_retry=retry, wave2_stale_retry=stale_retry,
                eligible_presented=int(truth.sum()), missed_presented=sum(remaining),
                work=stats['neural_work_counts'], free_roll_discrete_differences=total_discrete,
                max_latent_difference=largest, semantic_exact=True), raw


def bind_session(sessions, name):
    def bind(infer, buf, *args):
        original = {k:buf[k].clone() for k in ('state','meta','head','dyn','wm')}
        def reset():
            for k,x in original.items():buf[k].copy_(x)
            for k in ('regs','count','rhs','runs','writes','resumes','frontier','raw_trace','verdict'):
                if k in buf:buf[k].zero_()
        sessions[name] = (reset,infer,buf)
    return bind


def study(a):
    torch.set_num_threads(1)
    a.out.mkdir(parents=True, exist_ok=False)
    results = {}
    for case in a.cases:
        image,program,gold = inputs(a.corpus,a.ref,case)
        entries = load_catalog(image,program,a.ref/'sum-bits/program.json')
        with np.load(gold/'output.npz') as z:
            truth = {k:z[k] for k in ('runs','rhs','writes','resumes')}
        for seed in a.seeds:
            sessions,report,raws = {},{},{}
            variants = [('exact',None,False),('blind',0,False),('bits',1,False),
                                      ('ids',2,False),('shuffled',2,True),('masked',0,False)]
            if a.mask_study:
                variants = [('blind',0,False),('blind-guard',0,False),('ids',2,False),('ids-guard',2,False)]
            for name,mode,shuffle in variants:
                guard = name.endswith('-guard')
                folder = a.out/f'{case}-{seed}-{name}'
                cfg = None
                if mode is not None:
                    checkpoint = a.capture/f'train-{seed}-{2 if name=="masked" else mode}'
                    weights = read(checkpoint/'actor.json')
                    cfg = dict(catalog=entries, weights=weights['weights'], hidden=HIDDEN, rows=ROWS, ranks=RANKS,
                               waves=2, feedback=mode, receipt_head=True, shuffle_receipts=shuffle, exclude_closed=guard)
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,
                        neural=cfg,count_work=True)
                verify(folder,gold,image)
                if cfg:
                    report[name],raws[name] = audit(folder,a.capture/case,checkpoint,entries,mode,shuffle,guard)
                else:
                    report[name] = dict(semantic_exact=True, rhs=len(truth['rhs']))
                execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder.with_name(folder.name+'-timing'),
                        neural=cfg,measure_resident=bind_session(sessions,name))
                report[name]['ms'] = []
            for name,raw in raws.items():
                report[name]['changed_wave2_vs_ids'] = int((raw[:,2:,HIDDEN:]!=raws['ids'][:,2:,HIDDEN:]).any(-1).sum())
            arms = list(sessions)
            for trial in range(len(arms)*2):
                order = arms[trial%len(arms):]+arms[:trial%len(arms)]
                for name in (order if trial<len(arms) else order[::-1]):
                    reset,infer,buf = sessions[name]
                    reset();torch.mps.synchronize()
                    start = perf_counter_ns()
                    infer();torch.mps.synchronize()
                    report[name]['ms'].append((perf_counter_ns()-start)/1e6)
                    st = buf['state'].cpu().tolist()
                    assert st[7] and not st[5]
                    for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        got,want = buf[k][:st[i]].cpu().numpy(),truth[k]
                        if k=='rhs':
                            np.testing.assert_array_equal(got[:,:2],want[:,:2])
                            got,want = got[:,4:],want[:,4:]
                        np.testing.assert_array_equal(got,want)
                    if name!='exact':np.testing.assert_array_equal(buf['raw_trace'][:st[11]].cpu().numpy(),raws[name])
            for item in report.values():item['median_ms'] = median(item['ms'])
            results[f'{case}/{seed}'] = report
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,seed,[(k,v.get('committed'),round(v['median_ms'])) for k,v in report.items()],flush=True)
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--mask-study',action='store_true')
    with torch.inference_mode():study(p.parse_args())
