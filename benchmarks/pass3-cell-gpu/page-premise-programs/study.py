"""Compare fresh source reads, page-local dictionaries and compiler-emitted parent projections."""
import argparse,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paired_source',HERE.parent/'pair-source-frontier/study.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
MODES={'check':1,'rows':2,'wired':3,'shared':4,'points':5,'block':6}

def settings(req,a):
    off=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
    return {'off':off,**{n:dict(off,page_premises=MODES[n]) for n in a.arms}}

def observe(name,out,q,report):
    m=out['multi'];q['page']=m['premises']
    q['source_points']=m['counts']['point_reads']
    if name!='off':
        s=q['page'];assert s['audited']==s['tuples']==m['counts']['raw_tuples']
        assert s['logical_parents']==s['source_reads']+s['row_hits']
        assert s['source_reads']>0
        for key in ('raw','multi','physical','commits','children'):
            assert q[key]==report['off'][key],(name,key)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--arms',nargs='+',choices=MODES,default=list(MODES))
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    source.study(p.parse_args(),settings,observe,None)
