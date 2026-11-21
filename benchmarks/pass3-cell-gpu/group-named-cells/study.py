"""Compare identical forecasts allocated to a pool, named slots or an authorized page group."""
import argparse,importlib.util,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('wave_source',HERE.parent/'run-proposal-waves/study.py')
wave=importlib.util.module_from_spec(spec);spec.loader.exec_module(wave)


def settings(req,a):
    base=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,
              multi_page_tuples=8192,proposal_wave=65536)
    cfg=dict(timing='run',policy='score',weights=a.policy['models']['run']['coverage']['weights'],cap=a.cap)
    return {'off':base,**{k:dict(base,spec_cells=dict(cfg,storage=k)) for k in ('pooled','named','group')}}


def observe(name,v,q,rows):
    q['wave']=v['multi']['wave']
    q['score_digest']=v['single']['adaptive_rows']['decision_digest']
    wave_data=q['wave']
    assert wave_data['mixed_waves'] and wave_data['single_sets']==wave_data['verified_single_sets']
    assert wave_data['multi_sets']==wave_data['validated_multi_sets']
    if name=='off':return
    q['staging']=v['spec_cells']['counts'];c=q['staging']
    for k in ('raw','multi','commits','physical','children','wire_hash','score_digest'):
        assert q[k]==rows['off'][k],(name,k)
    assert c['offers_after_first_verify']==c['slots_after_first_verify']==0
    assert c['used']==c['payload_identity']==c['direct_fresh']+c['promoted']>0
    assert c['fresh']==q['root_allocated'] and c['used']+c['fallback']==c['fresh']
    if name!='pooled':
        for f in ('granted','preconstructed','fresh','offers','slots_before_first_verify','requested','clipped',
                  'header_capacity_bytes','private_payload_capacity_bytes','peak_slots','peak_private_bytes'):
            assert c[f]==rows['pooled']['staging'][f],(name,f)
    if name=='group':
        assert c['redeemed']==c['used'] and c['authorized_lanes']>c['used']
        assert c['redeemed_beyond_named']>0 and c['foreign_denials']==0
        assert rows['named']['staging']['used']<=c['used']<=rows['pooled']['staging']['used']


def faults(a):
    a.out.mkdir(parents=True,exist_ok=False)
    p,plans,req=wave.parent.common.config(a,'sum-bits')
    with wave.parent.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as ref:gold=ref({'audit':True})
    base=settings(req,a)['group'];results={}
    with wave.parent.base.session(a.native,p,plans) as infer:
        for name in ('none','stale','foreign','duplicate','withheld'):
            v=infer(dict(base,spec_cells=dict(base['spec_cells'],fault=name),audit=True))
            assert 'source_error' not in v,v.get('source_error')
            q=wave.parent.base.summarize(v,gold)
            q.pop('work');q.pop('rows')
            c=q['staging']=v['spec_cells']['counts']
            if name!='none':
                for k in ('rhs','raw','commits','physical','root_parents','root_ids','nested_ids','cells','state_sha','children'):
                    assert q[k]==results['none'][k]
            if name in ('stale','foreign','withheld'):
                assert c['used']==0 and c['fallback']==c['fresh']
                deny={'stale':'stale_named','foreign':'foreign_denials','withheld':'missing_named'}[name]
                assert c[deny]>0
            if name=='duplicate':
                assert c['used']==c['duplicate_denials']==results['none']['staging']['used']>0
            results[name]=q
    (a.out/'faults.json').write_text(json.dumps(results,indent=1)+'\n')
    print('fault denials',[(k,v['staging']['used'],v['staging']['duplicate_denials'],v['staging']['foreign_denials']) for k,v in results.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('exp','native','weights','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--cap',type=int,default=8192);p.add_argument('--faults',action='store_true')
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();a.policy=json.loads(a.weights.read_bytes())
    if a.faults:faults(a)
    else:wave.parent.study(a,settings,observe,None)
