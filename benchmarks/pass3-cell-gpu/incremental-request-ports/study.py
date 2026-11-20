"""Compare two representations of exactly the same learned reverse subscriptions."""
import argparse
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'request-route-policy'))
from driver import bridge,choices


def configure(req,a):
    off,route=choices(req,a)
    forward=dict(route,wake_roots=3)
    arms={'off':off,'offset':forward,
            **{name:dict(forward,patch_subscriptions=n) for n,name in enumerate(('rebuild','delta','union'),start=1)}}
    if getattr(a,'transfer_only',False):
        return {k:arms[k] for k in ('off','offset','union')}
    if a.lost_log:
        arms['lost-log']=dict(forward,patch_subscriptions=4)
    return arms


def inspect(name,out,q,report):
    q['patch']=out['multi']['patch_ports'];q['wake']=out['multi']['wake'];q['bridge']=out['multi']['bridges']
    if name in ('rebuild','delta','union','lost-log'):
        for key in ('raw','multi','commits','children','physical'):
            assert q[key]==report['offset'][key]
        assert q['bridge']['requests']==report['offset']['bridge']['requests']
        assert q['patch']['audit_rows']>0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--transfer-only',action='store_true')
    p.add_argument('--lost-log',action='store_true');p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    bridge.parent.common.config=bridge.config
    bridge.parent.study(p.parse_args(),configure,inspect,None)
