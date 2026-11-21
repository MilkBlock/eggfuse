"""Send an actually verified, same-page slot to root construction; check all original source faults."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('source_driver',HERE.parent/'pair-source-frontier/study.py')
source=importlib.util.module_from_spec(s);s.loader.exec_module(source)


def settings(req,a):
    ordinary=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
    typed=dict(ordinary,factor_page=2,page_premises=9,coordinate_verify=2)
    return {'off':ordinary,'coordinates':typed,'pass':dict(typed,verified_page_handoff=1),'buffer':dict(typed,verified_page_handoff=2)}


def observe(arm,v,row,report):
    w=v['root_recipe']['block_proofs'];row['handoff']=w
    if arm in ('pass','buffer'):
        assert w['accepted']==v['multi']['blocks']['completed']>0
        assert w['parent_headers_saved']+w['projected_headers_saved']==w['audit_headers']
        assert report['coordinates']['root_header_checks']-row['root_header_checks']==w['audit_headers']
        assert (w['exact_buffers']>0)==(arm=='buffer')
    if arm!='off':
        for f in ('raw','multi','wire_hash','physical','commits','children'):assert row[f]==report['off'][f]


def faults(infer,req,gold,rows):
    cfg=settings(req,None)['buffer']
    e=infer(dict(cfg,verified_page_handoff=3))
    assert 'foreign page lane' in e.get('source_error','')
    failures={'lane':[e['runs'],e['partial_rhs'],e['source_error']]}
    for n in (1,2,3):
        a=infer(dict(cfg,verified_page_handoff=1,multi_root_fault=n))
        b=infer(dict(settings(req,None)['coordinates'],multi_root_fault=n))
        assert a.get('source_error') and (a['source_error'],a['runs'],a['partial_rhs'])==(b.get('source_error'),b['runs'],b['partial_rhs'])
        failures[str(n)]=[a['runs'],a['partial_rhs'],a['source_error']]
    rows['off']['faults']=failures


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    source.study(p.parse_args(),settings,observe,faults)
