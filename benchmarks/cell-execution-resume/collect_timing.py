#!/usr/bin/env python3
"""Keep every timing sample, semantic stamp and the first work record per lane."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def collect(root,output):
    helpers=runpy.run_path(str(Path(__file__).resolve().parents[1]/'raytrace-parallel/collect.py'))
    result={'scope':'standalone Cell CPU, not native egglog','goal_achieved':False,
            'limits':'Interleaved small-sample full-process runs. Average cores includes loading '
                     'and export. Per-frontier wait includes dispatch and computation. '
                     'No independent effect scheduling or full utilization is established.',
            'workloads':{}}
    for case in ('sum','ray'):
        path=root/case/'samples.json';raw=json.loads(path.read_text())
        assert raw.get('finished_at_utc') and 'failure' not in raw
        work={'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'repeat':raw['repeat'],'warmups':raw['warmups'],
              'execution_order':raw['execution_order'],'semantic_reference':raw['semantic_reference'],
              'lanes':{},'comparisons':{}}
        for name,lane in raw['lanes'].items():
            samples=sorted(lane['samples'],key=lambda r:r['iteration'])
            assert [r['iteration'] for r in samples]==list(range(raw['repeat']))
            for row in lane['warmup_samples']+samples:
                assert {k:row[k] for k in raw['semantic_reference']}==raw['semantic_reference']
                assert row['runs']==(1428 if case=='sum' else 16883)
            def sample(r):
                v={k:r[k] for k in ['iteration','inference_seconds','process_wall_seconds',
                                   'process_user_seconds','process_system_seconds']}
                v['average_cores']=(r['process_user_seconds']+r['process_system_seconds'])/r['process_wall_seconds']
                if 'phases' in r:
                    v['phases'] = r['phases']
                return v
            work['lanes'][name]={
                'runtime_sha256':lane['runtime_sha256'],'program_file_sha256':lane['program_file_sha256'],
                'args':lane['args'],'warmup_samples':[sample(r) for r in lane['warmup_samples']],
                'samples':[sample(r) for r in samples],
                'inference':helpers['distribution']([r['inference_seconds'] for r in samples]),
                'process_wall':helpers['distribution']([r['process_wall_seconds'] for r in samples]),
                'average_cores':helpers['distribution']([sample(r)['average_cores'] for r in samples]),
                'first_execution_work':samples[0]['cell_execution'],
            }
        reference=sorted(raw['lanes']['current4']['samples'],key=lambda r:r['iteration'])
        for name,lane in raw['lanes'].items():
            rows=sorted(lane['samples'],key=lambda r:r['iteration'])
            work['comparisons'][name+'_over_current4']=helpers['paired_ratio'](
                [r['inference_seconds'] for r in reference],[r['inference_seconds'] for r in rows])
        result['workloads'][case]=work
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({c:{n:{k:v[k]['median'] for k in ('inference','process_wall','average_cores')}
                         for n,v in w['lanes'].items()} for c,w in result['workloads'].items()},indent=2))


if __name__=='__main__':
    if not __debug__:raise SystemExit('run without Python -O')
    collect(*map(Path,sys.argv[1:]))
