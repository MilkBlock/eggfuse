#!/usr/bin/env python3
"""Freeze, measure and summarize full Raytrace query-worker processes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import runpy
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def read(p): return json.loads(Path(p).read_text())
def save(p, v): Path(p).write_text(json.dumps(v, indent=2)+'\n')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def prepare(a):
    a.output.mkdir()
    old, new, program = [x.resolve() for x in [a.baseline, a.candidate, a.program]]
    configs = {'old_serial': (old, []), 'current_serial': (new, []),
        'query1_g64': (new, ['--query-workers','1','--query-grain','64']),
        'query2_g64': (new, ['--query-workers','2','--query-grain','64']),
        'query4_g64': (new, ['--query-workers','4','--query-grain','64']),
        'query4_g16': (new, ['--query-workers','4','--query-grain','16'])}
    manifest = {'lanes':{k:{'runtime':str(binary),'program':str(program),
        'args':['--local-congruence',*args]} for k,(binary,args) in configs.items()}}
    save(a.output/'manifest.json',manifest)
    save(a.output/'provenance.json',{
        'scope':'Standalone Cell CPU; complete Raytrace; not native egglog',
        'candidate_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'baseline_commit':'efc06d49 (runtime implementation 14e112c7; binary recorded at f4fd21cb)',
        'platform':platform.platform(),
        'cpu':subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip(),
        'logical_cpus':int(subprocess.check_output(['sysctl','-n','hw.logicalcpu'],text=True)),
        'features':'sparse-cells,view-ports,storage-metrics; ordinary release; no allocation/profiling instrumentation',
        'files':{k:{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
            for k,p in [('baseline',old),('candidate',new),('program',program)]},
        'input':'Same regenerated named Raytrace + frozen 64-block catalog + ownership query classes as raytrace-thread-bottlenecks; no source/catalog retraining.',
        'scope_limit':'Only query workers enabled; no guard-workers/overlap/scoped-execution. 1 is inline; 2/4 are pool sizes plus coordinator.',
        'semantics':'Exact final graph and all ordered Run signatures against old_serial; no independent native Raytrace proof.'})

def measure(a):
    harness = runpy.run_path(str(HERE.parent/'witness-prefix/measure.py'))
    harness['GROUPS']['query_workers'] = ('query_workers',)
    harness['measure'](read(a.manifest), a.output, a.repeat, a.warmups, a.timeout)

def collect(a):
    source = read(a.root/'timing/samples.json')
    assert source.get('finished_at_utc') and 'failure' not in source
    a.output.mkdir()
    helpers = runpy.run_path(str(HERE.parent/'raytrace-parallel/collect.py'))
    dist, ratio = helpers['distribution'], helpers['paired_ratio']
    lanes = source['lanes']
    summary = {'scope':source['scope'],'repeat':source['repeat'],'warmups':source['warmups'],
        'semantics':source['semantic_reference'],'lanes':{},'comparisons':{},
        'limits':'Small-sample interleaved full-process measurements. Worker entry counts are not query weights or CPU time. No independent native Raytrace semantic proof. No engine changes during measurement.'}
    for name,lane in lanes.items():
        rows=sorted(lane['samples'],key=lambda x:x['iteration'])
        assert [r['iteration'] for r in rows]==list(range(source['repeat']))
        for r in [*lane['warmup_samples'],*rows]:
            assert {k:r[k] for k in source['semantic_reference']}==source['semantic_reference']
            assert r['runs']==16883
        worker=[r.get('query_workers') or {'enabled':False} for r in rows]
        for q in worker:
            if q['enabled']:
                assert q['stats']['entries']==sum(q['stats']['worker_entries'])
        counts=[q.get('stats',{}).get('worker_entries',[]) for q in worker]
        summary['lanes'][name]={'args':lane['args'],'runtime_sha256':lane['runtime_sha256'],
            'program_file_sha256':lane['program_file_sha256'],
            'timing':{k:dist([r[k] for r in rows]) for k in ['inference_seconds','process_wall_seconds','load_seconds','setup_seconds','report_seconds','export_seconds','peak_rss_through_inference_bytes']},
            'phases':{k:dist([r['phases'][k] for r in rows]) for k in rows[0]['phases']},
            'process_average_cores':[(r['process_user_seconds']+r['process_system_seconds'])/r['process_wall_seconds'] for r in rows],
            'query_workers_first_sample':worker[0], 'worker_entries_per_sample':counts,
            'worker_max_mean_entry_ratio':[max(c)/(sum(c)/len(c)) if c and sum(c) else None for c in counts],
            'first_sample_work':{k:rows[0].get(k) for k in ['key_lookup_calls','stage_spine_stats','entry_schedule_stats','stats']},
            'samples':[{k:r[k] for k in ['iteration','inference_seconds','process_wall_seconds','process_user_seconds','process_system_seconds']} for r in rows]}
    for base in ['old_serial','current_serial','query1_g64']:
        reference=sorted(lanes[base]['samples'],key=lambda x:x['iteration'])
        summary['comparisons'][base]={}
        for name,lane in lanes.items():
            trial=sorted(lane['samples'],key=lambda x:x['iteration'])
            summary['comparisons'][base][name]={k:ratio([r[k] for r in reference],[r[k] for r in trial])
                for k in ['inference_seconds','process_wall_seconds']}
    save(a.output/'summary.json',summary)
    for name,path in [('samples.json',a.root/'timing/samples.json'),('provenance.json',a.root/'provenance.json'),('manifest.json',a.root/'manifest.json')]:
        shutil.copyfile(path,a.output/name)
    print(json.dumps({n:{k:lane['timing'][k]['median'] for k in ['inference_seconds','process_wall_seconds']} for n,lane in summary['lanes'].items()},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); commands=p.add_subparsers(dest='command',required=True)
    q=commands.add_parser('prepare')
    for n in ['baseline','candidate','program','output']: q.add_argument(n,type=Path)
    q=commands.add_parser('measure'); q.add_argument('manifest',type=Path);q.add_argument('output',type=Path)
    q.add_argument('--repeat',type=int,default=3);q.add_argument('--warmups',type=int,default=1);q.add_argument('--timeout',type=float,default=90)
    q=commands.add_parser('collect');q.add_argument('root',type=Path);q.add_argument('output',type=Path)
    a=p.parse_args();globals()[a.command](a)
