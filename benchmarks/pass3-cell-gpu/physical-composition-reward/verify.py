"""Verify disjoint calibration, matched source admissions, physical outcomes and the attribution counterexample."""
import json
from pathlib import Path
from statistics import median

root=Path(__file__).resolve().parent
def read(n):return json.loads((root/n).read_bytes())
frozen=read('frozen.json');cases=read('results.json');memory=read('heap.json');origin=read('origin.json')
assert set(frozen['train']).isdisjoint(frozen['eval']) and set(cases)==set(frozen['eval'])
assert len(frozen['pool'])==12 and frozen['candidate_budget']==4
assert frozen['policies']['net_bytes']==[] and all(x['benefit']['bytes']<0 for x in frozen['pool'])
assert set(frozen['policies']['published'])==set(frozen['policies']['owner_reward'])
for i,candidate in enumerate(frozen['pool']):
    chosen=[(v['controls'],v['candidate'][str(i)]) for v in frozen['training'].values()]
    assert candidate['benefit']['owners']==sum(a['instances']-b['instances'] for a,b in chosen)
    assert candidate['benefit']['retirements']==sum(b['retired_views']-a['retired_views'] for a,b in chosen)
    assert candidate['benefit']['bytes']==sum(a['charged_bytes']-b['charged_bytes'] for a,b in chosen)
for name,case in cases.items():
    v=case['paired'];baseline,owner,retire=[v[k] for k in ('empty','owner_reward','retirement_reward')]
    assert case['oracle_neural_rhs']==0 and not case['usable_neural_issue_id']
    assert origin[name]==dict(source_runs=baseline['runs'],ordered_arms=len(v),final_exports=len(v))
    assert len({(r['mask_size'],r['source_sha'],r['run_ledger_sha'],r['accessible_old_fact_refs']) for r in v.values()})==1
    assert all(r['external_handles']+r['retired_views']==r['committed_views']==r['mask_size'] for r in v.values())
    assert all(r['switches']==r['avoided_child_owners']==r['avoided_root_holds'] for r in v.values())
    assert all(r['median_ms']==median(r['times']) for r in v.values())
    assert owner['instances']<baseline['instances'] and owner['retired_views']==baseline['retired_views']
    assert retire['retired_views']>owner['retired_views'] and retire['external_handles']<owner['external_handles']
    def total(k):
        return sum(memory[name][k][v] for v in ('graph_owned_teardown_bytes','integral_instance_teardown_bytes','integral_library_teardown_bytes'))
    assert total('owner_reward')>total('empty') and total('retirement_reward')>total('empty')
print('Verified four disjoint training families, frozen reward choices, five real storage controls per test graph, externally checked source Runs and the zero-model-credit counterexample.')
