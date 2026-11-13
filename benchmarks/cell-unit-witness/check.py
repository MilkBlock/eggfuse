#!/usr/bin/env python3
"""Charge witness probes and source lookup avoidance separately."""
import json
from pathlib import Path
import runpy
import sys

base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-root-continuation/check.py'))


def collect(control, candidate):
    result = base['collect'](control, candidate, control_commit='b9b93023',
                             required_extra={'storage-prefix-units'})
    result['validation_attempts'] = base['read'](candidate / 'validation-attempts.json')
    for case, output in result['workloads'].items():
        reports = []
        for label, root in (('control', control), ('candidate', candidate)):
            report = base['read'](root / f'candidate-{case}/report.json')
            reports.append(report)
            metadata = report['cell_execution']['constructor_preparation']
            assert metadata['instance_bytes'] == 160 and metadata['inline_evidence_bytes'] == 32
            stats = report['stats']
            assert stats['rhs_context_suspends'] == stats['rhs_context_resumes']
            assert stats['rhs_suspend_holds'] == stats['rhs_suspend_releases']
            output.setdefault('unit_witness', {})[label] = {
                'metadata': metadata,
                'compiled_payload_bytes': report['cell_execution']['compiled_payload_bytes'],
                'query_task_counter_bytes': report['query_workers']['query_task_counter_bytes'],
                'preparation': report['query_workers']['stats']['execution'],
                'key_lookup_calls': report['key_lookup_calls'],
                'source': {k: v for k, v in stats.items() if k.startswith((
                    'unit_prepared_', 'constructor_prefix_', 'rhs_context_', 'rhs_suspend_'))},
            }
        # Existing Unit reuse must still perform the authoritative merge's
        # accounting at its original source effect position.
        assert reports[0]['stats']['merge_calls'] == reports[1]['stats']['merge_calls']
        new = output['unit_witness']['candidate']
        counts = new['preparation']['units']
        source = new['source']
        assert counts['continuation_bytes'] == counts['prefix_instances'] * 48
        assert source['unit_prepared_existing'] <= counts['existing'] <= counts['probes']
        assert source['unit_prepared_consumed'] <= counts['rows']
        output['unit_witness']['accounting'] = {
            'worker_probes_added': counts['probes'],
            'source_exact_lookups_skipped': source['unit_prepared_existing'],
            'note': 'Old key_lookup_calls excludes direct commit_unit_row interning. New worker probes are included; source witness skips are separate, not subtracted twice.',
        }
    assert result['workloads']['ray']['unit_witness']['candidate']['source']['unit_prepared_existing'] > 0
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Unit witnesses: exact state, source Runs, effects, merge accounting and native sum acceptance passed')
