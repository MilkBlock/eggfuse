#!/usr/bin/env python3
"""Keep every checkpoint timing sample and distinguish work from utilization."""
import json
from pathlib import Path
import runpy
import statistics
import sys


def collect(root, output):
    base = runpy.run_path(str(Path(__file__).with_name('collect.py')))
    read, sha = base['read'], base['sha']
    paired = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'raytrace-parallel/collect.py'))['paired_ratio']
    result = {'scope':'standalone Cell CPU, not native egglog', 'goal_achieved':False,
              'limits':'Process-average cores include loading, reporting and export, not just inference. '
                       'Per-task seconds are wall residence. Samples are interleaved on one machine; '
                       'small-sample bootstrap intervals do not establish a general scaling guarantee.',
              'workloads':{}, 'acceptance_sha256':sha(root / 'semantic-acceptance.json')}
    assert read(root / 'semantic-acceptance.json')['status'] == 'pass'
    effects = ('constructor_requests', 'function_updates', 'unions', 'logical_facts_created')
    for workload in ('sum', 'ray'):
        path = root / 'timing' / workload / 'samples.json'
        data = read(path)
        assert data.get('finished_at_utc') and 'failure' not in data
        reference = data['semantic_reference']
        assert reference['state_sha256'] == sha(root / workload / 'state.json')
        expected = {k:data['lanes']['current4']['samples'][0]['stats'][k] for k in effects}
        out = {'raw_samples_sha256':sha(path), 'repeat':data['repeat'], 'warmups':data['warmups'],
               'execution_order':data['execution_order'], 'semantic_reference':reference,
               'actual_effects':expected, 'lanes':{}, 'comparisons':{}}
        for name, lane in data['lanes'].items():
            detail = {k:lane[k] for k in ('args','runtime_sha256','program_file_sha256')}
            for kind in ('samples', 'warmup_samples'):
                rows = lane[kind]
                detail[kind] = []
                for row in rows:
                    assert {k:row[k] for k in reference} == reference
                    assert {k:row['stats'][k] for k in effects} == expected
                    entry = {k:row[k] for k in ('iteration','inference_seconds','process_wall_seconds',
                        'process_user_seconds','process_system_seconds','phases','key_lookup_calls')}
                    entry['process_average_cores'] = (row['process_user_seconds'] + row['process_system_seconds']) / row['process_wall_seconds']
                    expansion = row['query_workers'].get('residual_expansion',{}).get('stats',{})
                    entry['residual_completion'] = {k:v for k,v in expansion.items() if k.startswith('merge_') or k=='order_comparisons'}
                    if name.startswith('current') and name != 'current_serial':
                        assert expansion['merge_tasks'] == expansion['merge_inline_tasks'] + sum(expansion['merge_worker_tasks'])
                    detail[kind].append(entry)
            detail['medians'] = {k:statistics.median(r[k] for r in detail['samples']) for k in
                                 ('inference_seconds','process_wall_seconds','process_average_cores')}
            detail['first_sample_query_work'] = lane['samples'][0]['query_workers']
            detail['first_sample_publication_work'] = lane['samples'][0]['publication']
            out['lanes'][name] = detail
        for control, trial in [('checkpoint_serial','current_serial'),('checkpoint_serial','current4'),
                               ('before4','current4'),('current_serial','current4'),
                               ('current1','current4'),('current4','current8')]:
            out['comparisons'][trial+'_over_'+control] = {
                metric:paired([r[metric] for r in data['lanes'][control]['samples']],
                              [r[metric] for r in data['lanes'][trial]['samples']])
                for metric in ('inference_seconds','process_wall_seconds')}
        result['workloads'][workload] = out
    profile = read(root / 'profile/diagnostic.json')
    assert profile['runtime_sha256'] == sha(root / 'runtime')
    assert profile['state_sha256'] == result['workloads']['ray']['semantic_reference']['state_sha256']
    result['profile'] = {k:v for k,v in profile.items() if k not in ('threads','sample')}
    result['profile']['main_inference_inclusive'] = profile['threads'][0]['inference_inclusive']
    result['profile']['workers'] = [{'samples':t['samples'],'parked_samples':t['inclusive'].get('__psynch_cvwait',0)}
                                    for t in profile['threads'][1:]]
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({name:{k:v['medians'] for k,v in work['lanes'].items()}
                      for name,work in result['workloads'].items()},indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    collect(*(Path(a) for a in sys.argv[1:]))
