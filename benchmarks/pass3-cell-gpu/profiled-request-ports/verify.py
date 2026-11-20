"""Verify the actual measured joint native path and its disjoint frozen compiler profile."""
import json
from pathlib import Path
from statistics import median
from joint_common import HERE,DONORS,HOLDOUTS
from study_joint import ARMS,PROOFS,STREAM


def verify(folder):
    read=lambda path:json.loads(path.read_bytes())
    build=read(folder/'build-evidence.json');cases=read(folder/'results.json')
    old=read(HERE.parent/'native-backend-pgo/build-evidence.json')
    assert set(cases)==set(HOLDOUTS) and set(build['donors']['learned']['programs'])==set(DONORS)
    assert build['source_donors']==old['source_donors']
    assert build['vanilla_pgo']==old['binaries']['vanilla-use']['sha256']
    assert build['vanilla_profile']==old['donors']['vanilla']['profile_sha256']
    assert build['previous_neural_profile']==old['donors']['learned']['profile_sha256']!=build['donors']['learned']['profile_sha256']
    assert old['source_trees']['learned']['sha256']!=build['source_tree']['sha256']
    for name,r in build['donors']['learned']['programs'].items():
        x=old['donors']['learned']['programs'][name]
        assert all(r[k]==x[k] for k in ('runs','state','rhs','repetitions'))
        assert r['union_aware']['union_repairs']>0 and r['union_aware']['transferred']>0
    for mode,record in build['binaries'].items():
        assert record['runtime_codegen_units']==1 and not record['profile_warnings']
        if mode=='use':
            assert record['ir']['positive_entry_functions']>100 and 'multi-parent' in record['ir']['accounts']
            assert {'activation','subscriptions','connected'}&record['ir']['accounts'].keys()
        if mode=='plain':assert record['ir']['positive_entry_functions']==0
    for name,d in cases.items():
        r=d['arms'];assert set(r)==set(ARMS)
        assert set(tuple(sorted(o)) for o in d['orders'])=={tuple(sorted(ARMS))}
        for label,row in r.items():
            assert len(row['ms'])==len(row['api_ms'])==len(d['orders'])==4
            assert all(0<x<y for x,y in zip(row['ms'],row['api_ms']))
            assert median(row['ms'])==row['median_ms'] and median(row['api_ms'])==row['median_api_ms']
            for key in ('rhs','runs','state_sha'):assert row[key]==r['exact-release'][key]
            if label.startswith('exact'):continue
            assert all(row['checks'].values()) and row['remaining_rhs']==0 and row['direct_cells']*100>=row['fresh']*98
            for k in PROOFS:assert row[k]==r['plain-original'][k]
            paired=r['plain-union' if label.endswith('union') else 'plain-original']
            for k in STREAM+('root_allocated','raw_count','requests'):assert row[k]==paired[k]
            for k in ('patch','activation'):assert row[k]==paired[k]
            assert (row['activation']['routed_calls']>0)==label.endswith('union')
            assert (row['patch']['union_repairs']>0)==label.endswith('union')
    comparison=read(folder/'profile-transfer.json')
    assert set(comparison)==set(HOLDOUTS)
    for name,arms in comparison.items():
        assert set(arms)=={'original-trained','active-trained-off','active-trained-on'}
        for row in arms.values():
            assert len(row['ms'])==len(row['api_ms'])==4
            assert median(row['ms'])==row['median_ms'] and median(row['api_ms'])==row['median_api_ms']
            assert all(0<m<w for m,w in zip(row['ms'],row['api_ms']))
    return cases

if __name__=='__main__':print('Verified joint profile training and actual union-aware inference against default and separately profiled vanilla on',len(verify(HERE)),'held-out workloads')
