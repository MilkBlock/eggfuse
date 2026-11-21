"""Independent Run/physical ledgers, global-cap rounding and incorrect named attachments."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_inputs',HERE.parent/'pair-source-frontier/profile.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
base=common.base


def check(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        p,plans,req=common.config(a,case)
        req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
        with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as exact:
            gold=exact(dict(audit=True))
        with base.session(a.native,p,plans) as infer:
            arms={}
            settings={'off':None}
            for timing in ('run','page'):
                for storage in ('capacity','pooled','named'):
                    settings[timing+'/'+storage]=dict(timing=timing,storage=storage,policy='fixed',fixed=6,cap=37,capture=True)
            settings.update(zero=dict(timing='run',storage='pooled',policy='fixed',fixed=0,cap=37),
                over=dict(timing='run',storage='pooled',policy='fixed',fixed=100,cap=4096))
            for fault in ('withheld','stale'):
                settings[fault]=dict(timing='page',storage='named',policy='fixed',fixed=128,cap=256,fault=fault)
            for arm,cfg in settings.items():
                q=dict(req,audit=True)
                if cfg is not None:q['spec_cells']=cfg
                v=infer(q)
                assert 'source_error' not in v,(case,arm,v.get('source_error'))
                x=base.summarize(v,gold);x.pop('rows');x.pop('work')
                meta=v['spec_cells']
                x.update(counters=meta['counts'] if meta else {},samples=0)
                if arm=='off':
                    assert meta is None
                else:
                    for f in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids',
                              'rhs','direct_cells','raw','multi','physical','commits','children'):
                        assert x[f]==arms['off'][f],(case,arm,f)
                    stats=x['counters']
                    assert stats['fresh']==x['root_allocated'] and stats['committed']==x['applied'], (arm,stats,x['root_allocated'],x['applied'])
                    assert stats['fresh']==stats['used']+stats['fallback'] and stats['granted']==stats['used']+stats['unused']
                    assert stats['used']==stats['direct_fresh']+stats['promoted']
                    assert stats['granted']==stats['capacity_only']+stats['preconstructed']
                    assert stats['peak_slots']<=cfg['cap']
                    if arm=='zero':assert stats['used']==stats['granted']==0
                    elif arm in ('withheld','stale'):
                        assert stats['used']==0
                        assert stats['missing_named' if arm=='withheld' else 'stale_named']>0
                    else:
                        assert stats['used']>0 and stats['parent_mismatch']==0
                        if cfg['storage']=='capacity':assert stats['sampled_payloads']==0
                        else:assert stats['payload_identity']==stats['used']==stats['sampled_payloads']
                        if cfg['storage']=='named':assert 0<stats['used']<=stats['names_attached']
                    if cfg.get('capture'):
                        samples=meta['samples'];x['samples']=len(samples)
                        assert samples and all(len(s)==7 and len(s[3])==8 for s in samples)
                        assert sum(s[4] for s in samples)==stats['offers'] and sum(s[6] for s in samples)==stats['fresh']
                        assert sum(s[5] for s in samples)==stats['committed']
                        if cfg['timing']=='run':
                            groups={}
                            for epoch,rid,requested,granted,_,_ in meta['grants']:
                                groups.setdefault(epoch,[]).append((rid,requested,granted))
                            for group in groups.values():
                                n=sum(t[1] for t in group);cap=cfg['cap']
                                expected=[w if n<=cap else w*cap//n for _,w,_ in group]
                                if n>cap:
                                    order=sorted(range(len(group)),key=lambda i:-(group[i][1]*cap%n))
                                    for i in order[:cap-sum(expected)]:expected[i]+=1
                                assert expected==[t[2] for t in group]
                        else: assert all(s[3][-1]>0 and s[4]>0 for s in samples)
                arms[arm]=x
                print(case,arm, x['counters'].get('used'),flush=True)
            data[case]=arms
            (a.out/'controls.json').write_text(json.dumps(data,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seed',type=int,default=1703);check(p.parse_args())
