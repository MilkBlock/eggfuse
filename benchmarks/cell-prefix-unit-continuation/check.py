#!/usr/bin/env python3
"""Charge combined worker continuation without weakening semantic checks."""
import json
from pathlib import Path
import runpy
import sys

base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-root-continuation/check.py'))


def collect(control, candidate):
    result = base['collect'](control, candidate, control_commit='adfd0170',
        required_extra={'storage-prefix-units'})
    result['validation_attempts'] = base['read'](candidate / 'validation-attempts.json')
    for case, output in result['workloads'].items():
        for label, root in (('control', control), ('candidate', candidate)):
            report = base['read'](root / f'candidate-{case}/report.json')
            metadata = report['cell_execution']['constructor_preparation']
            assert metadata['instance_bytes'] == 160 and metadata['inline_evidence_bytes'] == 32
            stats = report['stats']
            assert stats['rhs_context_suspends'] == stats['rhs_context_resumes']
            assert stats['rhs_suspend_holds'] == stats['rhs_suspend_releases']
            output.setdefault('continuation', {})[label] = {
                'metadata': metadata,
                'compiled_payload_bytes': report['cell_execution']['compiled_payload_bytes'],
                'query_task_counter_bytes': report['query_workers']['query_task_counter_bytes'],
                'preparation': report['query_workers']['stats']['execution'],
                'source': {k: v for k, v in stats.items() if k.startswith((
                    'constructor_prefix_', 'unit_prepared_', 'constructor_prepared_', 'rhs_context_',
                    'rhs_suspend_', 'prepared_rhs_'))},
            }
        new = output['continuation']['candidate']
        counts = new['preparation']['units']
        assert counts['continuation_bytes'] == counts['prefix_instances'] * 48
    assert result['workloads']['ray']['continuation']['candidate']['preparation']['units']['prefix_rows'] > 0
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Prefix/Unit continuation: state, Run, effect and native sum acceptance passed')
