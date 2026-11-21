"""Compare identical compound family packets using a per-span loop or an indexed frontier."""
import argparse,json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
src=run_path(str(HERE.parent/'generative-pair-families/study.py'));wave=src['wave'];source=src['source']
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192;a.out.mkdir(parents=True,exist_ok=False)
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    result={}
    for case in ('sum-bits','3mm'):
        prog,plan,req=source.common.config(a,case);cfg=wave['settings'](req,a)['packed']
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as ref:gold=ref({'audit':True})
        rows={}
        with source.base.session(a.native,prog,plan) as run:
            arms={'span':dict(mode=2,compound=True),'sparse':dict(mode=2,compound=True,sparse_regions=True)}
            for name,opt in arms.items():
                v=run(dict(cfg,audit=True,birth_ledger=True,pair_family=dict(opt,trace=True)))
                q=src['observe'](v,gold);q.pop('examples',None);q['region_work']=z=v['multi']['sparse_regions']
                q['wire_sha']=v['multi']['sparse_wire_sha'];q['scalar']=v['multi']['compound_work'];f=q['stats'];emitted=q['explicit_packets']
                failures=z['keys_absent']+z['no_fresh_region']
                q['paid_negative_count']=failures;q['paid_decisions']=emitted+failures
                q['paid_fept']=q['visible']/q['paid_decisions']
                q['all_query_tests']=z['keys_probed']+z['epoch_checks']+z['binary_steps']
                q['all_query_events_with_setup']=emitted+q['all_query_tests']+z['construction_key_updates']+f['sender_marginal_rows']
                rows[name]=q
                if name=='sparse':
                    for k in (*src['KEYS'],'wire_sha','births','visible','birth_digest','visible_digest','expanded','raw_issue_sha','child_selected','child_decisions','group_accepted','group_visible','no_commit','no_visible','fept','strict_fept','all_scored','external_roots','rules'):
                        assert q[k]==rows['span'][k],(case,k)
                    for k in ('prototypes','absent','stale','private_rows','candidate_bound','actions','keys_issued','receiver_public_decodes','receiver_pairs','sender_marginal_rows','wire_bytes','upper_min_packets','matched_min_packets'):
                        assert f[k]==rows['span']['stats'][k],(case,k)
                print(case,name,z['keys_probed'],z['keys_absent'],z['no_fresh_region'],q['paid_fept'],flush=True)
            bad=run(dict(cfg,pair_family=dict(arms['sparse'],bad_scalar=True)));assert 'family' in str(bad.get('source_error',''));rows['fault']=bad['source_error']
            for i in range(5):
                seq=list(arms);seq=seq if i%2 else list(reversed(seq))
                for n in seq:
                    v=run(dict(cfg,pair_family=arms[n]))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if i:rows[n].setdefault('ms',[]).append(v['ms'])
            for n in arms:
                rows[n]['median_ms']=median(rows[n]['ms'])
                diag=run(dict(cfg,pair_family=dict(arms[n],phase=True)))
                assert diag['state_sha']==gold['state_sha']
                rows[n]['phase']={k:diag['multi']['family_work'][k] for k in ('issue_ms','receiver_ms')}
        result[case]=rows;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
if __name__=='__main__':main()
