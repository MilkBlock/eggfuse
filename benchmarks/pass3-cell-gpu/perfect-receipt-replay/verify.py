"""Require source parity; an oracle run can never establish model speed or neural discovery."""
from pathlib import Path
import json
from statistics import median

HERE=Path(__file__).resolve().parent


def verify(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    data={**read('results.json'),**read('deriche.json')}
    assert set(data)=={'sum-bits','conjugate-gradient','3mm','deriche'}
    for name,r in data.items():
        assert set(r)==({'vanilla','live','all','positive'} if name=='deriche' else {'vanilla','live','all','single','multi','positive'})
        ref=r['live']
        assert ref['online_root_rhs']==r['vanilla']['rhs'] and ref['direct_cells']*100>=98*ref['fresh']
        if name in ('sum-bits','deriche'):assert ref['wrong_site_rejected'] and ref['wrong_version_rejected']
        for k,v in r.items():
            assert len(v['ms'])==4 and median(v['ms'])==v['median_ms']
            if k=='vanilla':continue
            assert all(v['checks'].values()) and v['aligned']
            for f in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids','rhs','direct_cells','verified_source_rhs'):
                assert v[f]==ref[f]
            meta=v['tape']
            assert meta['single_replayed']==(k in ('single','all','positive')) and meta['multi_replayed']==(k in ('multi','all','positive'))
            assert (v['online_root_rhs']==0)==(k in ('all','positive'))
        for f in ('raw','multi','commits','physical','children','wire_hash','raw_multi','single_checked'):
            assert r['all'][f]==ref[f]
        assert r['positive']['raw_multi']<=r['all']['raw_multi'] and r['positive']['single_checked']<=r['all']['single_checked']
        if name!='deriche':assert r['single']['online_root_rhs']+r['multi']['online_root_rhs']==ref['rhs']
    phases=read('phases.json')
    for name,arms in phases.items():
        assert set(arms)=={'all','live','positive'}
        for v in arms.values():
            assert len(v)==3
            for s in v:assert abs(s['inference']-sum(x for k,x in s.items() if k!='inference'))<.001
    return data

if __name__=='__main__':print('Verified exact physical replay, original Run boundaries and explicit oracle attribution on',len(verify(HERE)),'complete passes')
