"""Check each plate's primary comparison against committed measurements (no training)."""
import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree

HERE=Path(__file__).resolve().parent
BENCH=HERE.parents[1]/'benchmarks/multi-row-generation'
SEEDS=(1703,1709)


@lru_cache(maxsize=None)
def table(study,file):
    with (BENCH/study/'results'/file).open() as f:return list(csv.DictReader(f,delimiter='\t'))


def value(study,field,file='metrics.tsv',**filters):
    hits=[r for r in table(study,file) if all(r[k]==str(v) for k,v in filters.items())]
    if len(hits)!=1:raise ValueError((study,filters,len(hits)))
    return int(hits[0][field])


def result(study,model,seed,panel,field):
    d=json.loads((BENCH/study/'results'/f'{model}-{seed}-result.json').read_text())
    return d['panels'][panel][field]


def check():
    if not __debug__:raise RuntimeError('run without -O')
    plates=json.loads((HERE/'plates.json').read_text())
    md=(HERE/'README.md').read_text()
    evidence=dict(re.findall(r'^- (S\d+)　\[.*?\]\(([^)]+)\)',md,re.M))
    assert len(plates)==20
    for i,p in enumerate(plates,1):
        assert p['id'].startswith(f'{i:02}-') and p['arms'] and p['measure'] and p['status'].startswith('已测')
        assert p['title'] in md and (HERE/'figures'/f"{p['id']}.svg").is_file()
        ElementTree.parse(HERE/'figures'/f"{p['id']}.svg")
        for key in re.findall(r'S\d+',p['src']):assert (HERE/evidence[key]).is_file()
    for j,seed in enumerate(SEEDS):
        def pair(a,b):return (a,b)[j]
        # 01–02: same held-out collision panel and role-controlled pointer heads.
        for arm,expected in [('shared_id',pair(4,1)),('shared_roles',pair(0,4)),('shared_pooled',pair(8,1)),
                             ('shared_ports',pair(1,3)),('private_roles',pair(3,0))]:
            assert value('port_ablation','nonempty_complete_graphs',arm=arm,seed=seed,subset='heldout_all',split='collision')==expected
        # 03–07: address, width, training, adaptive gates and readiness.
        for arm,expected in [('flat',pair(128,0)),('two',0),('three',0),('packed',128)]:
            assert value('address_ablation','whole_graphs',panel='new_port',model=f'{arm}-{seed}')==expected
        for width,expected in [(1,pair(175,312)),(2,pair(47,0)),(4,pair(2,0))]:
            assert value('width_ablation','nonempty_complete_graphs',subset='all',case=f'{seed}-{width}x{width}-parallel')==expected
        for arm,n in [('supervised',pair(175,347)),('team',pair(96,27)),('counterfactual',pair(99,0))]:
            assert value('credit_ablation','complete',model=f'{arm}-{seed}')==n
        assert value('gate_ablation','finish_skipped','lanes.tsv',lane=f'p25-calibrated-metal_skip-{seed}')==pair(0,4524)
        for lane in ('barrier_min','local',f'keyed-{seed}-guarded'):
            assert value('readiness_ablation','rust_exact',panel='heldout',schedule=lane)==512
        # 08–09: field projection and evidence erased at the second Run.
        for arm,mask,n in [('learned','none',pair(49,41)),('static','none',pair(39,37)),('aux','none',pair(65,67)),
                           ('aux','parents',pair(4,1)),('aux','parents_latent',pair(0,3))]:
            assert sum(value('crossrun','complete',arm=arm,mask=mask,seed=seed,split=s)
                       for s in ('left_collision','right_collision'))==n
        # 10–13 preserve the benchmark's own task and communication boundaries.
        for model,n in [('continuous',pair(10,6)),('typed',256)]:
            assert result('typed',model,seed,'cycle_tail','cumulative_exact_graphs')[-1]==n
        for study,arms in [('allocation',[('joint',pair(63,55)),('independent',pair(84,115))]),
                           ('coverage',[('control-joint',pair(63,55)),('coverage-joint',pair(78,156)),
                                        ('control-independent',pair(84,115)),('coverage-independent',pair(138,101))]),
                           ('streaming',[('blind',pair(94,80)),('feedback',pair(34,43))])]:
            for arm,n in arms:assert result(study,arm,seed,'iid-4x2','complete_graphs')==n
        assert result('streaming','feedback',seed,'iid-4x2-local','complete_graphs')==pair(35,44)
        # 14–19: the published endpoint and the stronger scoped contract are distinguished.
        for scope,n in [('global',pair(382,370)),('local',pair(378,360)),('certified',384)]:
            assert value('locality_ablation','nonempty_complete',seed=seed,scope=scope,workload='original',union_state='all')==n
        for mode,n in [('immediate',384),('fused_fenced',384),('late',96)]:
            assert value('union_ablation','all_observations_exact',seed=seed,panel='secondary',observers='after_locals',mode=mode)==n
        for mode,n in [('forward',pair(164,144)),('forward_joint',0)]:
            assert value('ownership_ablation','first_conflicts',seed=seed,panel='heldout',same_requests=0,transition_tick=1,mode=mode)==n
        for verifier in ('primitive','macro'):
            assert value('proof_ablation','complete',panel='heldout',seed=seed,source='neural',verifier=verifier)==pair(83,73)
        for mode,reused in [('primary',2868),('integral',4248),('stable_integral',1884)]:
            assert sum(value('integral_ablation',f'reuse_{i}',seed=seed,panel='heldout',mode=mode) for i in range(4))==reused
        for mode,budget,n in [('exact',8,330),('ledger_guard',8,252),('blind_raw',48,289),('blind_guard',48,384)]:
            assert value('stopping_ablation','complete',panel='heldout',seed=seed,transport='ordinary',lane=mode,budget=budget)==n
        # 20: same port identities with four different template encodings.
        for arm,n in [('explicit',pair(49,41)),('singleton',pair(79,34)),('pairwise',pair(61,65)),('incidence',pair(59,64))]:
            assert value('eclass_ablation','nonempty_complete',model=f'{arm}-{seed}',subset='heldout',state='all')==n
    print('All 20 primary comparisons, both seeds, diagrams and local source links verified.')


if __name__=='__main__':check()
