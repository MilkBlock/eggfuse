"""Frozen admission policies on whole held-out Pass 3 programs."""
import argparse,hashlib,json
from pathlib import Path
from driver import bridge,choices,control


def settings(req,a):
    off,route=choices(req,a)
    cfg={'off':off,'wake':control(route,2),'size-rule':control(route,4)}
    for name in a.arms:
        weights=a.weights[f'{name}-{a.policy_seed}']['weights']
        cfg[name]=control(route,3,weights=weights)
    return cfg


def observe(arm,out,q,rows):
    report=out['multi']['route_gate']
    q['gate']=dict(calls=report['calls'],choices=report['choices'])
    q['wake']=out['multi']['wake']
    samples=report['samples']
    assert len(samples)==report['calls'] and sum(bool(s[3]) for s in samples)==report['choices']
    q['route_contexts']=hashlib.sha256(json.dumps([s[:3] for s in samples],separators=(',',':')).encode()).hexdigest()
    q['route_actions']=''.join('1' if s[3] else '0' for s in samples)
    if arm=='off':assert report['calls']==0
    elif arm=='wake':assert 0<report['calls']==report['choices']
    else:
        assert report['calls']==rows['wake']['gate']['calls']
        assert q['route_contexts']==rows['wake']['route_contexts']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','policy','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--arms',nargs='+',choices=['bandit-0','bandit-8','return-0','return-8'],default=['bandit-0','return-0','bandit-8','return-8'])
    p.add_argument('--policy-seed',type=int,default=1703)
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();a.weights=json.loads(a.policy.read_bytes())
    bridge.parent.common.config=bridge.config
    bridge.parent.study(a,settings,observe,None)
