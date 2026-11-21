"""Check online rank attribution against an independent source and offline replay bounds."""
import argparse,hashlib,importlib.util,json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('independent',HERE.parent/'pair-source-frontier/profile.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
ref=common.base


def sigmoid_free_logit(x, mode, hidden=False):
    if mode=='zero':return 0.
    v=x[2]/8
    return math.tanh(v) if hidden else v


def bounds(groups, scorer):
    low=high=oracle=lanes=positive=0
    for ep,rid,grant,bins in groups:
        ranked={}
        for x,n,y in bins:
            b=ranked.setdefault(scorer(x),[0,0]);b[0]+=n;b[1]+=y
            lanes+=n+y;positive+=y
        oracle+=min(grant,sum(y for _,_,y in bins))
        remaining=grant
        for score,(negative,yes) in sorted(ranked.items(),reverse=True):
            use=min(remaining,negative+yes)
            low+=max(0,use-negative);high+=min(use,yes)
            remaining-=use
    return low,high,oracle,lanes,positive


def controls(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        program,plans,request=common.config(a,case)
        request.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,
                       multi_page_tuples=8192,proposal_wave=65536,audit=True)
        with ref.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as get: gold=get({'audit':True})
        ranked=[0.]*12;ranked[2]=1.
        hidden=[[0.]*12 for _ in range(8)];hidden[0][2]=1.
        named=dict(storage='named',timing='run',policy='fixed',cap=37,fixed=6)
        scenarios={
            'legacy':{},
            'first':{'lane_rank':{'mode':'first','groups':True}},
            'zero':{'lane_rank':{'mode':'score','weights':[0.]*12}},
            'reverse':{'lane_rank':{'mode':'score','weights':ranked}},
            'hidden':{'lane_rank':{'mode':'score','hidden':hidden,'hidden_bias':[0.]*8,'output':[1.]+[0.]*7}},
            'stale':{'lane_rank':{'mode':'score','weights':ranked},'fault':'stale'},
            'withheld':{'lane_rank':{'mode':'score','weights':ranked},'fault':'withheld'},
            'foreign':{'lane_rank':{'mode':'score','weights':ranked,'fault':'foreign'}},
            'zero-cap':{'lane_rank':{'mode':'capture','groups':True},'cap':0},
        }
        rows={};observations=[]
        with ref.session(a.native,program,plans) as infer:
            for arm,delta in scenarios.items():
                raw=infer(dict(request,spec_cells=dict(named,**delta)))
                assert 'source_error' not in raw,(case,arm,raw.get('source_error'))
                record=ref.summarize(raw,gold);record.pop('rows');record.pop('work')
                if arm!='legacy':
                    for key in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids',
                                'nested_ids','rhs','direct_cells','raw','multi','commits','physical','children'):
                        assert record[key]==rows['legacy'][key],(case,arm,key)
                meta=raw['spec_cells']; c=meta['counts']; q=meta['lane_rank']; rc=q['counts']
                record['staged']=c
                assert c['fresh']==record['root_allocated'] and c['used']+c['fallback']==c['fresh']
                assert c['used']==c['payload_identity'] and c['granted']==c['used']+c['unused']
                if arm=='legacy':
                    assert q['counts']['lanes']==0
                else:
                    record['rank']=rc
                    assert rc['fresh_lanes']==c['fresh'] and rc['lanes']==c['offers']
                    assert rc['selected']==rc['before_verifier'] and not rc['unlisted_fresh'] and not rc['repeated_fresh']
                    assert c['complete_before_verify_runs']==c['nonempty_wave_runs']
                    if arm in ('first','zero','reverse','hidden','zero-cap'):
                        assert c['used']==rc['selected_fresh'] and c['names_attached']==rc['selected'] and not c['parent_mismatch']
                    if arm in ('first','zero'):
                        assert c['used']==rows['legacy']['staged']['used']==rc['first_fresh']
                    if arm in ('first','zero-cap'):
                        hist=q['hist'];groups=q['groups']
                        assert sum(n+y for x,(n,y) in hist)==c['offers']
                        assert sum(y for _,(_,y) in hist)==c['fresh']
                        assert sum(n+y for _,_,_,v in groups for _,n,y in v)==c['offers']
                        assert sum(y for _,_,_,v in groups for _,n,y in v)==c['fresh']
                        assert any(k==0 for _,_,k,_ in groups)
                        record['hist_sha256']=hashlib.sha256(json.dumps(hist,separators=(',',':')).encode()).hexdigest()
                        record['groups']=len(groups)
                        if arm=='first':
                            observations=groups
                        else:
                            assert not c['granted'] and record['hist_sha256']==rows['first']['hist_sha256']
                    if arm in ('reverse','hidden'):
                        lo,hi,oracle,n,p=bounds(observations,lambda x:sigmoid_free_logit(x,'reverse',arm=='hidden'))
                        assert lo<=rc['selected_fresh']<=hi and rc['oracle_fresh']==oracle and n==c['offers'] and p==c['fresh']
                        assert rc['scored'] and rc['beyond_first_chosen']
                        record['independent_tie_bounds']=[lo,hi]
                    if arm in ('stale','withheld','foreign'):
                        name={'stale':'stale_named','withheld':'missing_named','foreign':'parent_mismatch'}[arm]
                        assert c['used']==0 and c[name]==rc['selected_fresh']>0
                rows[arm]=record;print(case,arm,c['used'],rc['first_fresh'],rc['oracle_fresh'],flush=True)
        assert rows['reverse']['staged']['used']==rows['hidden']['staged']['used']
        data[case]=rows;(a.out/'controls.json').write_text(json.dumps(data,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    controls(p.parse_args())
