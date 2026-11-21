"""Recover every sample and reproduce the CPU-calibrated first-passage metrics."""
from pathlib import Path
import json
from analyze import summarize
from plot import unpack

HERE=Path(__file__).resolve().parent
ARMS={'cpu','raw','filter','packed','ports','fraction','coverage'}


def verify():
    curves=json.loads((HERE/'curves.json').read_bytes())
    evidence=json.loads((HERE/'audit.json').read_bytes())
    assert set(curves)==set(evidence)=={'sum-bits','3mm'}
    for case,x in curves.items():
        assert set(x['rows'])==ARMS
        all_runs=[*x['calibration'],*(r['sampled'] for pairs in x['rows'].values() for r in pairs)]
        for record in all_runs:
            record['trace']=[list(r) for r in unpack(record)]
        assert len(x['order'])==2*4*len(ARMS)
        for name in ARMS:
            assert all([t for i,k,t in x['order'] if k==name and i==j] in ([True,False],[False,True]) for j in range(4))
            assert [t for _,k,t in x['order'] if k==name][::2].count(True)==2
        ref=evidence[case]['reference']
        assert all((r['runs'],r['state_sha'])==(ref['runs'],ref['state_sha']) for r in x['calibration'])
        for k,a in evidence[case]['arms'].items():
            assert all(a['checks'].values())
            if k=='raw':continue
            for ledger in ('rhs','cells','state_sha','root_parents','root_ids','nested_ids','children','single_winners','multi_winners','multi'):
                assert a['source'][ledger]==evidence[case]['arms']['raw']['source'][ledger],(case,k,ledger)
            for ledger in ('raw','commits','physical'):
                assert a['source'][ledger]==evidence[case]['arms']['filter']['source'][ledger],(case,k,ledger)
    s=summarize(curves,evidence)
    assert s==json.loads((HERE/'results.json').read_bytes())
    for case,report in s.items():
        assert report['calibrated_rise_mib']>0
        for arm in report['arms'].values():
            for target in arm['median']['thresholds'].values():assert sum(target['outcomes'].values())==4
    print('Verified independent CPU thresholds, 6 calibration and 112 rotated measurement processes, complete source audits and all inference-only OS RSS/Cell trajectories.')


if __name__=='__main__':verify()
