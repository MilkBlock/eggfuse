"""Run-wide online prediction and private physical staging with a compiled page verifier."""
import argparse,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('wave_staging',HERE/'study.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

def configure(req,a):
    modes=entry.settings(req,a)
    return {'off':modes['off'],'wave':modes['wave'],'all-lanes':modes['all-lanes'],
            'block':dict(modes['wave'],page_premises=7),
            'named-block':dict(modes['named'],page_premises=7),
            'eager-block':dict(modes['all-lanes'],page_premises=7)}

def observe(k,v,row,g):
    entry.wave.observe(k,v,row,g)
    row['block']=v['multi']['blocks']
    spec=v.get('spec_cells');row['staging']=spec.get('counts') if isinstance(spec,dict) else None
    if k.endswith('block'):
        assert row['block']['completed']>0
    if k in ('all-lanes','named-block','eager-block'):
        s=row['staging'];assert s['used']==s['payload_identity']>0
        assert s['offers_after_first_verify']==s['slots_after_first_verify']==0
    if k=='eager-block':
        for f in ('requested','granted','used','unused','fresh','payload_identity'):
            assert row['staging'][f]==g['all-lanes']['staging'][f]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['3mm']);p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();a.policy=json.loads(a.weights.read_bytes());entry.wave.parent.study(a,configure,observe,None)
