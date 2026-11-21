"""Carry the exact same emitted tuples into either a flat/expanded verifier or direct word verification."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('factors',HERE.parent/'factored-receipt-pages/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
ARMS={'encoded':(2,0,0),'hash-block':(2,9,0),'words':(2,9,1),
      'ports':(2,9,2),'eager':(2,9,3),'adaptive-columns':(3,9,2),'stream':(4,9,2)}


def settings(req,a):
    off=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=a.size)
    arms={'off':dict(off,factor_page=0)}
    for name in a.arms:
        f,p,w=ARMS[name]
        cfg=dict(off,factor_page=f)
        if p:cfg['page_premises']=p
        if w:cfg['coordinate_verify']=w
        arms[name]=cfg
    return arms


def observe(name,out,q,prior):
    q.update(words=out['multi']['word_verifier'],block=out['multi']['blocks'],factor=out['root_recipe']['factor'],
             parent_work=out['multi']['premises'],source_points=out['multi']['counts']['point_reads'])
    if name!='off':
        for key in ('raw','multi','wire_hash','wire_bytes','commits','physical','children'):
            assert q[key]==prior['off'][key],(name,key)
    if name in ('words','ports','eager','adaptive-columns','stream'):
        assert q['words']['pages']>0 and q['words']['audited']==out['multi']['counts']['raw_tuples']
        assert q['words']['loaded']<=q['words']['words'] and q['words']['cap_fallbacks']==0
        if name in ('ports','eager','adaptive-columns','stream'):
            assert q['words']['port_maps']>0
        if 'hash-block' in prior:
            ref=prior['hash-block']
            fields=['started','completed','stale','key_misses','guard_failures','value_slots']
            # A direct column assigns different coordinates to repeated source addresses.
            if name in ('words','ports','eager'):
                fields+=['parent_port_hits','avoided_key_fields']
            for key in fields:
                assert q['block'][key]==ref['block'][key],(name,key)


def fault(infer,req,gold,report):
    req.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
    v=infer(dict(req,factor_page=2,page_premises=9,coordinate_verify=2,factor_fault=True))
    assert 'coordinate' in v.get('source_error',''),v.get('source_error')
    assert v['partial_rhs']<gold['rhs_count']
    report['off']['fault']={'error':v['source_error'],'runs':v['runs'],'partial_rhs':v['partial_rhs']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',default=list(ARMS),choices=ARMS)
    p.add_argument('--size',type=int,default=8192)
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    base.paired.study(p.parse_args(),settings,observe,fault)
