"""Compare public learned-key regions to the same frozen group and singleton issuer."""
import argparse,json
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
compound=run_path(str(HERE.parent/'compound-fept-model/study.py'))
wide=compound['wide'];src=wide['src'];weights=wide['joint']['pair_weights']
def settings(req,a,trace):
    unchanged=compound['settings'](req,a,trace)['compound']
    modes={"compound":0,"large_explicit":3,"region":1,"learned":2}
    return {name:dict(unchanged,pair_family=dict(unchanged['pair_family'],region_mode=mode,region_weights=weights))
            for name,mode in modes.items() if name in a.arms}

def main(a):
    a.out.mkdir(parents=True,exist_ok=True);all_rows={}
    for case in a.cases:
        p,plan,req=src.common.config(a,case);program=json.loads(p.read_bytes());audit=settings(req,a,True);normal=settings(req,a,False)
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as native:gold=native({'audit':True})
        rows={};faults={}
        with src.base.session(a.native,p,plan) as run:
            for name,cfg in audit.items():
                v=run(dict(cfg,audit=True,birth_ledger=True));assert 'source_error' not in v,(case,name,v.get('source_error'))
                z=rows[name]=wide['analyze'](case,v,gold,program,'joint');r=z['region']=v['multi']['region_work']
                z['compound_work']=v['multi']['compound_work']
                z['unadjusted_decisions']=z['denominators']['all_prototype_decisions']
                z['denominators']['all_prototype_decisions']+=r['model_calls']
                z['denominators']['decisions_plus_return']+=r['model_calls']
                z['denominators']['paid_plus_empty_prefixes']=z['denominators']['paid_groups']+r['empty_prefixes']
                z['per_packet']={k:z['visible']/n for k,n in z['denominators'].items()}
                if name in ('learned','region'):
                    f=z['family_counts']
                    assert f['wire_bytes']==128*f['actions']==128*r['physical_windows']
                    assert r['digest_keys_sender']==r['digest_keys_receiver'] and r['max_keys']<=256 and r['max_pairs']<=4096
                    assert r['model_calls']>=r['chosen_splits']
                baseline=rows['compound']
                for k in wide['FIXED']:assert z[k]==baseline[k],(case,name,k)
                assert z['family_counts']['private_rows']==baseline['family_counts']['private_rows']
                assert z['arity']==baseline['arity']
                print(case,name,z['family_counts']['actions'],z['family_counts']['candidate_bound'],z['family_counts']['wire_bytes'],z['visible'],z['denominators']['forward'],z['per_packet']['forward'],flush=True)
                del v
            cfg=normal['learned']
            for fault,why in (('bad_region_keys','region public learned-key coverage mismatch'),('fault','region public pair extent mismatch')):
                v=run(dict(cfg,pair_family=dict(cfg['pair_family'],**{fault:True})));err=v.get('source_error','');assert ('region' in err and (why in err or 'region scope' in err)),err
                faults[fault]=[v['runs'],err]
            if not a.smoke:
                names=list(rows)
                for i in range(1+a.repeats):
                    seq=names[i%len(names):]+names[:i%len(names)]
                    for name in seq if i%2 else reversed(seq):
                        t=perf_counter();v=run(normal[name]);ms=1000*(perf_counter()-t)
                        assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                        assert rows[name]['root_allocated']==v['root_recipe']['allocated'] and rows[name]['family_counts']['actions']==v['multi']['family_work']['actions']
                        if i:rows[name]['ms'].append(v['ms']);rows[name]['wall_ms'].append(ms)
                for name,z in rows.items():
                    z.update(median_ms=median(z['ms']),median_wall_ms=median(z['wall_ms']))
                    cfg=normal[name];v=run(dict(cfg,pair_family=dict(cfg['pair_family'],phase=True)));assert v['state_sha']==gold['state_sha']
                    z['diagnostic_ms']={k:v['multi']['family_work'][k] for k in ('source_pair_ms','issue_ms','receiver_ms')}
        all_rows[case]={'runs':gold['runs'],'faults':faults,'arms':rows}
        (a.out/'results.json').write_text(json.dumps(all_rows,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--arms',nargs='+',default=['compound','large_explicit','region','learned'])
    p.add_argument('--smoke',action='store_true');p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();wide['joint']['common'](a);main(a)
