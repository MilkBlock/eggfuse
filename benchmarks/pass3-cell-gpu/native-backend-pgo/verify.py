"""Check native profile use, train/test separation, source provenance and paired execution timings."""
import json
from pathlib import Path
from statistics import median
from pgo_common import ARMS,PROOFS,DONORS,HOLDOUTS

HERE=Path(__file__).resolve().parent


def verify(folder):
    load=lambda f:json.loads((folder/f).read_bytes())
    build=load('build-evidence.json');results=load('results.json')
    assert set(results)==set(HOLDOUTS) and set(build['source_donors'])==set(DONORS)
    train={obj['program_sha256'] for obj in build['source_donors'].values()}
    assert len(train)==len(DONORS)
    for kind,meta in build['donors'].items():
        assert kind in ('vanilla','learned') and set(meta['programs'])==set(DONORS)
        assert len(meta['profile_sha256'])==64 and meta['functions']>100
        for p in meta['programs'].values():assert p['repetitions']==3 and p['rhs']>0 and p['raw_bytes']>0
        variants=[build['binaries'][kind+'-'+arm] for arm in ('plain','generate','use')]
        assert all(x['runtime_codegen_units']==1 for x in variants)
        assert variants[0]['ir']['positive_entry_functions']==0
        ir=variants[2]['ir'];assert ir['positive_entry_functions']>100 and ir['accounts']['graph']['max_entry_count']>0
        if kind=='learned':
            assert ir['accounts']['multi-parent']['max_entry_count']>0 and ir['accounts']['single-parent']['max_entry_count']>0
        assert not variants[2]['profile_warnings'] and len({x['sha256'] for x in variants})==3
    overlap=load('overlap.json')
    assert set(overlap)==set(HOLDOUTS) and build['original_release']['learned_runtime_codegen_units']==16
    for name,items in overlap.items():
        assert set(items)=={'learned','vanilla'}
        for kind,v in items.items():
            assert v['donor_sha256']==build['donors'][kind]['profile_sha256']!=v['heldout_sha256']
            assert 0<v['edge_percent']<=100 and v['test_edges']>0 and v['donor_edges']>0 and v['overlap_functions']>100
    for case,data in results.items():
        arms=data['arms']; assert set(arms)==set(ARMS) and data['program_sha256'] not in train
        for arm in ARMS:
            row=arms[arm]
            assert sum(o[0]==arm for o in data['orders'])==1
            assert len(row['ms'])==len(row['roundtrip_ms'])==len(data['orders'])==6
            assert row['median_ms']==median(row['ms']) and row['median_roundtrip_ms']==median(row['roundtrip_ms'])
            assert all(0<x<y for x,y in zip(row['ms'],row['roundtrip_ms']))
            assert row['state_sha']==arms['vanilla-release']['state_sha'] and row['rhs']==arms['vanilla-release']['rhs']
            if arm.endswith('release'):
                assert data['binaries'][arm]==build['original_release'][arm.split('-')[0]+'_sha256']
            else:assert data['binaries'][arm]==build['binaries'][arm]['sha256']
            if arm.startswith('learned'):
                assert all(row['checks'].values()) and row['remaining_rhs']==0
                assert 100*row['direct_cells']>=98*row['fresh'] and row['multi_tuples']>0
                assert all(row[k]==arms['learned-release'][k] for k in PROOFS)
    return results


if __name__=='__main__': print('Verified separate native PGO profiles, linked runtime code generation and full source/Cell ledgers on',len(verify(HERE)),'held-out workloads.')
