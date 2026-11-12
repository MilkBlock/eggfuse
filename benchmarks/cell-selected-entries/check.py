#!/usr/bin/env python3
"""Check selected Entry ranges against the preceding actual CPU execution."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def scalar_work(values):
    return {k: v for k, v in values.items() if isinstance(v, (int, bool)) and not k.endswith('_ns')}


def work(report):
    return {'queries': scalar_work(report['query_workers']['stats']),
            'expansions': scalar_work(report['query_workers']['residual_expansion']['stats'])}


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU work and semantic checks, not timing or native egglog performance',
        'control_commit': 'f90011bc',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'initial_runtime_sha256': sha(candidate / 'initial/candidate-runtime'),
        'limits': 'Source filters and Cursor ownership still select mixed-rule Entries. Task counts and capacity are not elapsed-time savings. Selected arena cumulative capacity repeatedly counts the same retained buffer; growth measures payload capacity added, not total allocation traffic. Answer span inline storage is already part of event headers; only heap spill is additional.',
        'workloads': {},
    }
    assert result['candidate_runtime_sha256'] == read(candidate / 'manifest.json')['runtime_sha256']
    for case in ('sum', 'ray'):
        a, initial, b = (read(root / f'candidate-{case}/report.json')
                         for root in (control, candidate / 'initial', candidate))
        state = sha(control / f'candidate-{case}/state.json')
        runs = [[s[k] for k in keys] for s in a['steps']]
        for root, doc in ((candidate / 'initial', initial), (candidate, b)):
            assert doc['status'] == a['status'] == 'complete'
            assert a['program_sha256'] == doc['program_sha256']
            assert state == sha(root / f'candidate-{case}/state.json')
            assert runs == [[s[k] for k in keys] for s in doc['steps']]
            assert all(a['stats'][k] == doc['stats'][k] for k in effects)
            assert a['sieve']['stats'] == doc['sieve']['stats']
            assert a['key_lookup_calls'] == doc['key_lookup_calls']
            for k in ('entries', 'answers', 'steps', 'point_reads', 'result_writes', 'guards', 'guard_rejections', 'owner_rejections'):
                assert a['query_workers']['stats'][k] == doc['query_workers']['stats'][k], k
            for k in ('partitioned_entries', 'partitioned_admitted', 'partitioned_answers', 'column_prepares',
                      'entries', 'answers', 'input_rows', 'point_reads', 'expansion_rows', 'run_pool_calls'):
                assert a['query_workers']['residual_expansion']['stats'][k] == doc['query_workers']['residual_expansion']['stats'][k], k
        old, new = work(a), work(b)
        q, e = new['queries'], new['expansions']
        selected = q['selected_range_entries']
        assert selected == e['partitioned_entries'] > 0
        assert old['queries']['entry_headers'] - q['entry_headers'] == selected
        assert old['expansions']['queued_row_owners'] - e['queued_row_owners'] == selected
        assert q['entry_range_row_borrows'] == q['entry_range_rows']
        assert e['queued_row_owners'] + q['entry_range_rows'] == e['input_rows']
        assert q['entry_range_batches'] < q['entry_range_chunks']
        assert q['chunks'] < old['queries']['chunks'] < work(initial)['queries']['chunks']
        assert q['event_bytes'] < old['queries']['event_bytes']
        assert q['frame_cache_borrows'] == q['chunks']
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_and_run_summaries': True,
            'logical_effects_query_steps_and_all_sieve_counters_equal': True,
            'key_lookup_calls': b['key_lookup_calls'],
            'work': {'control': old, 'initial': work(initial), 'candidate': new},
        }
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Entry ranges, exact states, Run summaries and native sum contract verified')
