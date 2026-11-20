"""Compare real sealed page encodings on the same learned source and commit program."""
import argparse,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paired_page',HERE.parent/'pair-source-frontier/study.py')
paired=importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
ARMS={'direct':1,'dictionary':2,'selective':3,'stream':4}


def choices(req,a):
    off=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,
             multi_page_tuples=8192,factor_page=0)
    return {'off':off,**{n:dict(off,factor_page=i) for n,i in ARMS.items()}}


def observe(name,result,q,arms):
    meta=q['page']=result['root_recipe']['factor']
    assert meta['pages']==result['multi']['pages']>0
    assert meta['refs']==result['multi']['counts']['raw_root_slots']>0
    assert meta['canonical_wire_bytes']==meta['audited_wire_bytes']>0 and meta['encoded_wire_hash']!=0
    if name=='off':
        assert meta['flat_pages']==meta['pages']
    else:
        off=arms['off']
        for k in ('raw','wire_hash','wire_bytes','emitted','commits','physical','multi','children','cells','single_winners','multi_winners','root_parents','nested_ids','root_ids'):
            assert q[k]==off[k],(name,k)
        assert meta['checked_refs']==meta['refs'] and meta['packed_pages']==meta['pages']
        assert meta['body_bytes']==meta['word_bytes']+meta['role_bytes']+meta['lane_bytes']
        assert meta['coordinate_faults']==0
    if name=='stream':
        assert meta['streamed_pages']==meta['pages']
        for k in ('pages','refs','body_bytes','retained_bytes','canonical_wire_bytes','encoded_wire_hash','direct_roles','dictionary_roles','constant_roles','word_bytes','lane_bytes','role_bytes'):
            assert meta[k]==arms['selective']['page'][k],k


def faults(infer,req,gold,report):
    cfg=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
    invalid=infer(dict(cfg,factor_page=2,factor_fault=True))
    assert 'invalid encoded parent coordinate' in invalid.get('source_error',''),invalid.get('source_error')
    report['off']['invalid_coordinate']={'run':invalid['runs'],'failure':invalid['source_error']}
    for flag in (1,2,3):
        old=infer(dict(cfg,factor_page=0,multi_root_fault=flag))
        new=infer(dict(cfg,factor_page=4,multi_root_fault=flag))
        assert old['source_error']==new['source_error'] and old['runs']==new['runs'] and old['partial_rhs']==new['partial_rhs']
        report['off'].setdefault('source_faults',{})[str(flag)]={'run':old['runs'],'rhs':old['partial_rhs'],'failure':old['source_error']}
    good=infer(dict(cfg,factor_page=4))
    assert good['multi']['total_rhs']==gold['rhs_count'] and good['state_sha']==gold['state_sha']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    paired.study(p.parse_args(),choices,observe,faults)
