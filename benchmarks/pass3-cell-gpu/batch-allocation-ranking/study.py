"""Evaluate frozen decisions under exactly the same physical budget and complete signed stream."""
import argparse,json
from pathlib import Path
from driver import source,request
ARMS=('feature','zero','bce-0','quota-0','bce-8','quota-8')

def configure(req,a):
    off=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536)
    first=request(req)
    options={'off':off,'first':first}
    for key in a.arms:
        if key=='feature':options[key]=request(req,'feature-first')
        elif key=='zero':options[key]=request(req,'score',weights={'weights':[0.]*12,'bias':0.})
        else:options[key]=request(req,'score',weights=a.models[f'{key}-{a.seed}'])
    return options

def observe(arm,v,q,rows):
    q['scores']=v['single']['adaptive_rows']['decision_digest']
    if arm=='off':return
    w=v['spec_cells'];c=w['counts'];r=w['lane_rank']['counts']
    q.update(staging=c,rank=r)
    assert c['slots_after_first_verify']==c['offers_after_first_verify']==0
    assert c['used']==c['payload_identity']==r['selected_fresh'] and r['before_verifier']==r['selected']
    assert r['unlisted_fresh']==r['repeated_fresh']==0 and r['fresh_lanes']==q['root_allocated']
    for f in ('raw','multi','physical','commits','children','wire_hash','scores'):assert q[f]==rows['off'][f],(arm,f)
    if arm!='first':
        base=rows['first']
        for f in ('granted','preconstructed','fresh','requested','clipped','peak_slots','slots_before_first_verify'):
            assert c[f]==base['staging'][f]
        for f in ('lanes','selected','first_fresh','fresh_lanes','oracle_fresh','partial_rules'):
            assert r[f]==base['rank'][f]
        if arm in ('feature','zero'):assert r['selected_fresh']==base['rank']['selected_fresh']
        if arm!='feature':assert r['scored']>0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','policy','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--arms',nargs='+',choices=ARMS,default=list(ARMS));p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--repeats',type=int,default=4);a=p.parse_args();a.models=json.loads(a.policy.read_bytes())['models']
    source.study(a,configure,observe,None)
