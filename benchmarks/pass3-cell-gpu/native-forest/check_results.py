"""Validate actual production attribution across the three hardware placements."""
from pathlib import Path
import json
from statistics import median


def check(file):
    results=json.loads(file.read_text())
    for case,r in results.items():
        a,b,m=[r[n] for n in ('cpu-rust','mps-rust','mps-metal')]
        assert a['certificate']['sha256']==b['certificate']['sha256']
        assert a['certificate']['bytes']==b['certificate']['bytes']
        for arm in [a,b,m]:
            assert arm['first_divergence'] is None and arm['rhs']==arm['children']+arm['compiler_roots']+arm['exact']
            assert len(arm['timings'])==6 and arm['median_ms']==median(s['total_ms'] for s in arm['timings'])
        assert a['children']==b['children'] and a['compiler_roots']==b['compiler_roots']==m['compiler_roots']==2
        assert r['rust-no-residual']['exact']==r['metal-no-residual']['exact']==0
        assert r['rust-no-residual']['first_divergence']==r['metal-no-residual']['first_divergence']==3
        assert r['rust-wrong-parent']['children']==0
        for control in ('assisted','no-residual'):
            audit=r['cross-'+control]
            assert audit['acceptance']=='pass' and audit['typed_graph'] and all(n==audit['runs'] for n in audit['aligned'].values())
        origins=r['origins']
        assert a['children']==origins['same_source_rhs']+len(origins['only_native'])+len(origins['different_ordinal'])
        assert m['children']==origins['same_source_rhs']+len(origins['only_metal'])+len(origins['different_ordinal'])
    print('All three placements validated for',len(results),'workload/seed pairs.')


if __name__=='__main__':check(Path(__file__).resolve().parent/'results.json')
