"""Compare authenticated staged records moved at commit with same-address resident header slabs."""
import argparse,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location("groups",HERE.parent/"group-named-cells/study.py")
group=importlib.util.module_from_spec(s);s.loader.exec_module(group)
source=group.wave.parent

def settings(req,a):
    cfg=group.settings(req,a)
    base=cfg['group']
    return {'off':cfg['off'],'move':base,**{f'resident-{w}':dict(base,spec_cells=dict(base['spec_cells'],resident_headers=True,page_width=w)) for w in a.widths}}

def observe(name,v,q,r):
    q['score']=v['single']['adaptive_rows']['decision_digest'];q['wave']=v['multi']['wave']
    if name=='off':return
    for field in ('raw','multi','physical','commits','children','wire_hash','score'):assert q[field]==r['off'][field],(name,field)
    q['private']=v['spec_cells']['counts'];q['store']=v['resident_slabs']
    c=q['private']
    assert c['used']==c['payload_identity']>0 and c['offers_after_first_verify']==c['slots_after_first_verify']==0
    if name!='move':
        for f in ('used','granted','unused','fresh','fallback','redeemed','offers_before_first_verify'):
            assert c[f]==r['move']['private'][f],(name,f)
        w=q['store'];assert w['published']==w['same_address']==c['used'] and w['old_run_reads']>0
        assert w['alive']+w['held_holes']==w['occupied_slots']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    p.add_argument('--widths',nargs='+',default=[16,64,256],type=int)
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();a.cap=8192;a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes())
    source.study(a,settings,observe,None)
