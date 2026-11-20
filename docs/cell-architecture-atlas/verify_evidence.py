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
    assert len(plates)==55
    for i,p in enumerate(plates,1):
        assert p['id'].startswith(f'{i:02}-') and all(p[k] for k in ('q','arms','fix','measure','note','src'))
        if i<=37:
            assert p['status'].startswith(('已测','实跑'))
        else:
            if i in (38,39,40,41,46,55):assert p['status'].startswith('已测')
            else:assert p['status']=='待验证 · 实验设计'
            arms=p['diagram']
            assert len(arms)>=2 and len({a['title'] for a in arms})==len(arms)
            for a in arms:
                assert 2<=len(a['layers'])<=4
                assert all(1<=len(layer)<=2 and all(k in 'nswvt' and txt for k,txt in layer) for layer in a['layers'])
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
    folder=BENCH.parent/'pass3-cell-gpu/results'
    report=json.loads((folder/'ingress-and-pass3.json').read_text())
    other=json.loads((folder/'distinct-graphs.json').read_text())
    assert report['shared_initial']
    for name,n,args,tokens in [('sum-bits',223,342,[3747,3518]),('dot-product',320,583,[3565,3138])]:
        item=report['cases'][name]
        assert item['ingress']['roundtrip_exact'] and item['ingress']['ordered_arguments']==145
        assert other[name]['rows']==n and other[name]['ordered_arguments']==args and other[name]['roundtrip_exact']
        assert len(item['input_matrix'])==4 and all(v['fully_checked_runs']==3 for v in item['input_matrix'].values())
        trial=item['rows']['2']
        assert trial['tokens']==tokens and trial['cross_row_duplicates']==0 and trial['same_as_one_row']
        assert trial['device_done'] and not trial['full_typed_graph_equal'] and trial['acceptance']=='incomplete'
    integrated=json.loads((folder/'integration.json').read_text())
    release=json.loads((folder/'release-check.json').read_text())['cases']
    primitives=json.loads((folder/'typed-scalars.json').read_text())
    assert [primitives[m]['wrong'] for m in ('integer','guarded','lossy')]==[0,0,279]
    timing=json.loads((folder/'cli.json').read_text())
    for name,n,res,raw,overlap in [('sum-bits',1428,2098,[3369,3868],28),('dot-product',1535,1835,[3572,3126],6)]:
        r=integrated[name];rep=release[name]
        assert r['reference']['acceptance']==rep['fresh_acceptance']=='pass' and rep['fresh_runs']==n
        assert r['reference']['gpu_continuations']==r['reference']['cpu_continuations']==res
        assert all(r['aligned'][k]==n and rep['fresh_source_digests'][k]==n for k in ('schedule','rhs','writes','spine','known_class_roots'))
        assert r['native_contract']['status']==rep['fresh_native_status']=='pass'
        assert r['ordering']['fenced_published']['full_typed_graph_equal'] and r['ordering']['immediate_canonical']['first_write_count_difference']
        a=r['variants']
        assert all(k in a for k in ('matched_scan','matched_point','matched_hash','run_batch_1','run_batch_4','run_batch_16'))
        assert len(a)==26 and a['two']['token_bank_bytes']<a['cap_32']['token_bank_bytes']<a['packed_32']['token_bank_bytes']
        assert rep['emissions']['parity']['exclusive']==raw and rep['emissions']['parity']['both_proposed']==overlap
        assert all(min(rep['emissions'][arm]['exclusive'])>0 for arm in ('parity','1703','1709'))
        assert all(len(v['samples'])==3 for v in timing[name].values())
        with (folder/f'{name}-runs.tsv').open() as f:
            rows=list(csv.DictReader(f,delimiter='\t'))
        assert len(rows)==n and sum(int(r['spine_count']) for r in rows)==res
    profile=json.loads((folder.parent/'profile/results/profile.json').read_text())['cases']
    for n,runs in [('sum-bits',1428),('dot-product',1535)]:
        item=profile[n]
        for arm in ('baseline','prefix'):
            phases=item['modes'][arm]['detail']
            assert phases['verified'] and phases['runs']==runs and len(phases['groups_ms'])==6
            assert abs(sum(phases['groups_ms'].values())-phases['phase_sum_ms'])<1e-5
            assert item['checks'][arm]['acceptance']=='pass'
        assert item['modes']['prefix']['work']['dfs_iterations']<item['modes']['baseline']['work']['dfs_iterations']
        assert len(item['cold']['prefix']['samples'])==8
    hybrid=json.loads((folder.parent/'hybrid/results.json').read_text())
    for n,runs,hits in [('sum-bits',1428,3043),('dot-product',1535,2092)]:
        lanes=hybrid[n]
        for lane,trial in lanes.items():
            assert trial['state_sha256']==lanes['cpu']['state_sha256'] and trial['audit']==lanes['cpu']['audit']
            assert all(trial['audit'][k]['runs']==runs for k in ('rhs','writes','resumes'))
            assert len(trial['samples'])==10
            if lane!='cpu':
                assert all(s['admitted']==hits and s['tokens']==hits and s['device_dispatches']>0 for s in trial['samples'])
        cpu, batch=lanes['cpu']['median'],lanes['batched']['median']
        if n=='sum-bits':
            assert (cpu['residual_candidates'],batch['residual_candidates'],batch['device_dispatches'],batch['device_pairs'])==(8769,5583,369,4824849)
        else:
            assert (cpu['residual_candidates'],batch['residual_candidates'],batch['device_dispatches'],batch['device_pairs'])==(8022,5834,324,5156042)
        assert lanes['retired']['median']['retired_nodes']==19
        assert lanes['batched']['median']['device_dispatches']<lanes['native']['median']['device_dispatches']
        for k in ('residual_candidates','entry_packets','node_notifications','parameter_copies'):
            assert lanes['retired']['median'][k]==lanes['native']['median'][k]<lanes['cpu']['median'][k]
    unique=json.loads((folder.parent/'unique-parent/results.json').read_text())
    for n,hits,wrong,recovered in [('sum-bits',889,6509,209),('dot-product',952,8176,389)]:
        lanes=unique['cases'][n]; model=lanes['model']; counts=model['counts']
        assert lanes['native_status']=='pass' and lanes['null_control']['coverage']==hits
        assert counts['wrong_parent']==wrong and counts['recovered_wrong_parent']==recovered
        assert counts['from_proposal']+recovered==hits and counts['missed_by_abstention']==0
        assert model['audited_parent_addresses']==counts['proposals']
        for k in ('point','model','metal'):
            assert lanes[k]['admitted_bindings']==hits and lanes[k]['audit']==lanes['cpu']['audit']
            assert lanes[k]['state_sha256']==lanes['cpu']['state_sha256'] and len(lanes[k]['samples'])==8
    sets=json.loads((folder.parent/'set-memory/results.json').read_text())
    for lane in ('full','full-probes','union','dynamic'):
        c=sets['cases'][lane]
        assert c['audit']['acceptance']=='pass' and c['audit']['full_typed_graph_equal']
        assert len(c['isolated']['opened'])==5
    assert sets['cases']['full']['helper_rhs']==4 and sets['cases']['full-probes']['audit']['completed']==835
    assert sets['cases']['dynamic']['integer_writes'][-1]['old']=={'Int':2}
    assert sets['cases']['dynamic']['integer_writes'][-1]['new']=={'Int':1} and sets['negative']['gpu_fault']==12
    block=json.loads((folder.parent/'block-ceiling/results.json').read_text())
    for n,dfs,rep in [('sum-bits',2605,284230),('dot-product',2119,224346)]:
        t=block[n];base=t['records']['tally'];end=t['records']['notified']
        assert t['dfs_saved']==dfs==sum(base['credits']) and base['dfs']-end['dfs']==dfs
        assert t['repair_with_incidence_ceiling']==rep==base['repair_scan']-end['repair_scan']
        assert base['outside_scan']==end['outside_scan'] and t['dispatches_saved']==0 and end['final']
        assert end['aligned']['writes']==end['aligned']['rhs']==end['aligned']['spine']==t['source_runs']
    import runpy
    repair=folder.parent/'co-repair'
    runpy.run_path(str(repair/'verify.py'))['verify'](repair)
    signals=json.loads((folder.parent/'key-signals/results.json').read_text())
    for seed in SEEDS:
        for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
            lanes=signals[f'{case}/{seed}']; baseline=lanes['single-8']; target=lanes['double_hash-8']
            assert target['counts']['ambiguous_present_keys']<baseline['counts']['ambiguous_present_keys']
            assert baseline['counts']['ambiguous_present_keys']==lanes['single-16']['counts']['ambiguous_present_keys']
            for arm,data in lanes.items():
                assert len(data['samples'])==10 and data['counts']['bindings']==baseline['counts']['bindings']
                assert all(data[k]==baseline[k] for k in ('rhs','writes','spine','final','runs'))
        assert signals[f'sum-bits/{seed}']['double_hash-8']['counts']['from_proposal']==889
    region=folder.parent/'region-admission'
    bounded=json.loads((region/'results.json').read_text())
    strata=json.loads((region/'strata.json').read_text())
    for n,v in bounded.items():
        arms=v['arms']
        for k,a in arms.items():
            assert len(a['samples_ms'])==8 and a['exact'] and a['runs']==arms['full']['runs']
            if k=='full':continue
            assert a['index_bytes']<arms['full']['index_bytes'] and a['maintenance'][3]<=32
            assert sum(t['saved_clean_rows'] for t in strata[n][k].values())==a['price']['clean_rows_saved']
            assert arms['hindsight']['price']['priced_work']>=a['price']['priced_work']
    print('Verified 43 measured plates, 12 pending designs, and all diagrams.')


if __name__=='__main__':check()
