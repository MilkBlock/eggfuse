"""Predict a whole wave, allocate real private Cells, seal addresses, then verify and publish in source order."""
import argparse,importlib.util,json,math
from pathlib import Path

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('wave_source',HERE.parent/'run-proposal-waves/study.py')
wave=importlib.util.module_from_spec(s);s.loader.exec_module(wave)

def settings(req,a):
    off=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
    batch=dict(off,proposal_wave=65536)
    normal=dict(timing='run',policy='score',weights=a.policy['models']['run']['coverage']['weights'],cap=8192)
    high=list(normal['weights']);high[0]+=math.log(2)
    return {'off':off,'wave':batch,'reserve':dict(batch,spec_cells=dict(normal,storage='capacity')),
       'pool':dict(batch,spec_cells=dict(normal,storage='pooled')),
       'named':dict(batch,spec_cells=dict(normal,storage='named')),
       'optimistic':dict(batch,spec_cells=dict(normal,storage='named',weights=high,cap=32768)),
       # A page has now actually been emitted by the model. Bet one physical record
       # on every lane; only the normal verifier and ordered allocator can publish it.
       'all-lanes':dict(batch,spec_cells=dict(timing='page',policy='score',storage='named',cap=32768,weights=[0.]*7+[1.]))}

def observe(name,v,q,rows):
    wave.observe(name,v,q,rows)
    s=v.get('spec_cells')
    q['staging']=s.get('counts') if isinstance(s,dict) else None
    if name not in ('off','wave'):
        assert q['staging'] and q['staging']['granted']>0
        if name!='reserve':
            stats=q['staging']
            assert stats['used']>0 and stats['preconstructed']>0
        assert q['wave']['sealed_multi']==rows['wave']['wave']['sealed_multi'] and q['wave']['sealed_single']==rows['wave']['wave']['sealed_single']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('exp','native','weights','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();a.policy=json.loads(a.weights.read_bytes())
    wave.parent.study(a,settings,observe,None)
