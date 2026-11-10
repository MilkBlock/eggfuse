#!/usr/bin/env python3
"""Keep compact evidence for Cell-instance Run tasks without rerunning workloads."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('root',type=Path);p.add_argument('prior_raytrace_summary',type=Path);p.add_argument('output',type=Path)
a=p.parse_args();a.output.mkdir(exist_ok=True)
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x): p.write_text(json.dumps(x,indent=2)+'\n')
checks=read(a.root/'final/checks.json'); semantic=read(a.root/'final/semantic-acceptance.json')
assert semantic['status']=='pass'
ray=read(a.root/'raytrace-final/report.json'); prior=read(a.prior_raytrace_summary)
keys=['ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed']
run_hash=hashlib.sha256(json.dumps([[s[k] for k in keys] for s in ray['steps']],separators=(',',':')).encode()).hexdigest()
assert ray['status']=='complete' and len(ray['steps'])==16883
assert run_hash==prior['semantics']['schedule_sha256']
assert sha(a.root/'raytrace-final/state.json')==prior['semantics']['state_sha256']
result={'scope':'Standalone Cell CPU; finite source Run read-only Cell tasks; not native egglog',
    'baseline_commit':'13cfd235','binaries':checks['binaries'],'semantic_acceptance':semantic,
    'short_cases':{},'raytrace':{'runs':len(ray['steps']),'semantics':prior['semantics'],
        'before':prior['lanes']['query4_g64']['query_workers_first_sample'],
        'after':ray['query_workers'],'key_lookup_calls':ray['key_lookup_calls'],
        'current_report_sha256':sha(a.root/'raytrace-final/report.json')}}
for name,case in checks['cases'].items():
    result['short_cases'][name]={'program_sha256':case['program_sha256'],
        'lanes':{n:{'runs':r['runs'],'hashes':r['hashes'],'query_workers':r['query_workers'],
                    'key_lookup_calls':r['key_lookup_calls']} for n,r in case['lanes'].items()}}
save(a.output/'checks.json',result)
samples=read(a.root/'timing/samples.json');assert samples.get('finished_at_utc') and 'failure' not in samples
helpers=runpy.run_path(str(Path(__file__).parents[1]/'raytrace-parallel/collect.py'))
dist,ratio=helpers['distribution'],helpers['paired_ratio']
summary={'scope':samples['scope'],'baseline_commit':'13cfd235','repeat':samples['repeat'],
    'warmups':samples['warmups'],'semantics':samples['semantic_reference'],'lanes':{},'comparisons':{},
    'limits':'3 interleaved repetitions on an interactive machine; worker/counter changes are not a proof of thread scaling.'}
for name,lane in samples['lanes'].items():
    rows=sorted(lane['samples'],key=lambda r:r['iteration'])
    assert [r['iteration'] for r in rows]==list(range(samples['repeat']))
    for r in [*lane['warmup_samples'],*rows]:
        assert {k:r[k] for k in samples['semantic_reference']}==samples['semantic_reference']
        assert r['runs']==16883
        q=r['query_workers']
        if q['enabled']:
            assert q['stats']['entries']==sum(q['stats']['worker_entries'])+q['stats'].get('coordinator_entries',0)
    summary['lanes'][name]={'args':lane['args'],'runtime_sha256':lane['runtime_sha256'],
        'program_sha256':lane['program_file_sha256'],
        'timing':{k:dist([r[k] for r in rows]) for k in ['inference_seconds','process_wall_seconds','setup_seconds','peak_rss_through_inference_bytes']},
        'phases':{k:dist([r['phases'][k] for r in rows]) for k in rows[0]['phases']},
        'worker_entries':[r['query_workers'].get('stats',{}).get('worker_entries',[]) for r in rows],
        'worker_steps':[r['query_workers'].get('stats',{}).get('worker_steps',[]) for r in rows],
        'average_process_cores':[(r['process_user_seconds']+r['process_system_seconds'])/r['process_wall_seconds'] for r in rows]}
for base in ['before_serial','before_query4','cell_serial']:
    ref=sorted(samples['lanes'][base]['samples'],key=lambda r:r['iteration']);summary['comparisons'][base]={}
    for name,lane in samples['lanes'].items():
        rows=sorted(lane['samples'],key=lambda r:r['iteration'])
        summary['comparisons'][base][name]={k:ratio([r[k] for r in ref],[r[k] for r in rows]) for k in ['inference_seconds','process_wall_seconds']}
save(a.output/'timing-summary.json',summary)
# Retain timing samples without replicating unchanged graphs/reports or binary artifacts.
shutil.copyfile(a.root/'timing/samples.json',a.output/'timing-samples.json')
shutil.copyfile(a.root/'timing-manifest.json',a.output/'timing-manifest.json')
print(json.dumps({n:l['timing']['inference_seconds']['median'] for n,l in summary['lanes'].items()}))
