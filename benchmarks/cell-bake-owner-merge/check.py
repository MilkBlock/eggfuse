#!/usr/bin/env python3
"""Validate the owner merge against frozen parallel and composed-owner inputs."""
import json
from pathlib import Path
import runpy
import sys

base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-root-continuation/check.py'))


def collect(control, candidate):
    result = base['collect'](control, candidate, control_commit='26b1650b',
        required_extra={'storage-prepared', 'integration-cell_ownership',
                        'storage-fact-lifecycle', 'batch-examples', 'batch-python',
                        'batch-owner-replay'})
    result['merged_branch'] = 'codex/cell-structural-compression'
    result['merged_commit'] = 'b563e90cda050d71f658deae634e94a2ce905261'
    for case, output in result['workloads'].items():
        for label, root in (('control', control), ('candidate', candidate)):
            report = base['read'](root / f'candidate-{case}/report.json')
            scheduler = report['cell_execution']['runtime']['stats']['scheduler']
            for key in ('prepared_resumptions', 'prepared_key_fallbacks', 'completed_without_queue'):
                output['work'][label]['scheduler'][key] = scheduler.get(key, 0)
            assert report['stats']['rhs_context_suspends'] == report['stats']['rhs_context_resumes']
            assert report['stats']['rhs_suspend_holds'] == report['stats']['rhs_suspend_releases']
        # Ownership compression is opt-in, not silently enabled for this lane.
        assert report['stats']['shared_owner_extensions'] == 0
        assert report['stats']['shared_owner_extension_frames'] == 0
    batch = candidate / 'batch'
    frozen = base['read'](batch / 'frozen-inputs.json')
    for record in frozen['files']:
        assert base['sha'](batch / record['file']) == record['sha256']
    checks = base['read'](batch / 'owned-state/checked.json')
    assert {c['case'] for c in checks['cases']} == {
        c['case'] for c in base['read'](batch / 'manifest.json')['cases']}
    replay = []
    for case in checks['cases']:
        name = case['case']
        observed = base['read'](batch / name / 'catalog-observation.json')
        program = base['read'](batch / 'owned-state' / name / 'candidate.json')
        assert case['all_saved_run_checks_equal'] is True
        assert case['runs'] == observed['runs'] == len(observed['run_checks'])
        assert case['final_state'] == observed['final_state']
        assert case['program'] == program['sha256']
        assert case['source_storage']['completed_owners']['completed_frames'] > 0
        assert case['source_storage']['completed_owners']['owned_fact_bytes'] == 32
        replay.append({k: v for k, v in case.items() if k != 'source_storage'})
        replay[-1]['completed_owners'] = case['source_storage']['completed_owners']
    result['batch_owner_replay'] = replay
    result['frozen_batch_inputs'] = frozen
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Owner merge: exact Runs, states, effects and native sum acceptance passed')
