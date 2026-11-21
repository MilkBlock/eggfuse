"""Compare compiler and learned pre-enumeration union position certificates at full source execution."""
import argparse,json
from pathlib import Path
from common import source,settings


def choices(req,a):
    off=settings(req);w=a.model
    lookup={'static':(2,'strict',True),'owner':(3,'strict',False),'strict':(3,'strict',True),'broad':(3,'broad',True),
            'combined':(4,'strict',True),'baked':(4,'strict',True),'enumerate':(5,'strict',True)}
    arms={'off':off}
    for arm in a.arms:
        mode,threshold,parents=lookup[arm]
        arms[arm]=dict(off,union_locator=dict(mode=mode,parent_ports=parents,bake=arm=='baked',weights=w['weights'],bias=w['bias'],threshold=w['thresholds'][threshold]))
    return arms


def observe(arm,out,row,report):
    row['locations']=out['union_locator']['stats'];row['examples']=out['union_locator']['examples']
    if arm!='off':
        v=row['locations'];assert v['unions']>0 and v['true_positions']>0
        assert v['true_proposed']+v['false_proposed']==v['proposed_fields']
        assert v['applied']==v['audits'] and v['verified_facts']>=v['applied']
        assert v['total_readers']==v['direct_notifications']+v['ordinary_notifications']
        for f in ('raw','multi','physical','commits','children'):
            assert row[f]==report['off'][f]


def stale(infer,req,gold,report):
    req=choices(req,arguments)['combined'];bad=infer(dict(req,union_locator=dict(req['union_locator'],mode=6),audit=True))
    v=bad['union_locator']['stats']
    assert v['expired']>0 and v['applied']==v['direct_notifications']==0
    assert all(bad[k]==gold[k] for k in ('rhs','writes','resumes','schedule','runs','state_sha'))
    assert [[e for e in row if e[0]=='union'] for row in bad['events']]==gold['unions']
    report['off']['stale_position_receipts']=v['expired']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--arms',nargs='+',choices=['static','owner','strict','broad','combined','baked','enumerate'],default=['static','owner','strict','broad','combined','baked','enumerate'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    arguments=p.parse_args();arguments.model=json.loads(arguments.weights.read_bytes())
    source.study(arguments,choices,observe,stale)
