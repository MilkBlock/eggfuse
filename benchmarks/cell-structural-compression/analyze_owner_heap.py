#!/usr/bin/env python3
"""Compare requested-heap traces against an already audited final-state digest.

This is a memory observation, not semantic proof or a timing benchmark.
"""
import json
import sys
from pathlib import Path


def analyze(control, takeover, audit):
    if control['mode'] != 'record-control' or takeover['mode'] != 'inherited-owners':
        raise ValueError('matched source-record capacity control required')
    for trace in (control, takeover):
        if trace['program_sha256'] != audit['program_sha256']:
            raise ValueError('program differs from audit')
        if trace['final_state_sha256'] != audit['final_state_sha256']:
            raise ValueError('final state differs from audited execution')
        if trace['runs'] != audit['modes'][0]['runs']:
            raise ValueError('source Run count differs')
        if len(trace['samples']) != trace['runs']:
            raise ValueError('incomplete heap samples')
        if sum(v for _, v in trace['graph_fields']) + trace['graph_unlisted_teardown_bytes'] != trace['graph_owned_teardown_bytes']:
            raise ValueError('Graph teardown accounting does not balance')
    fields = [dict(t['graph_fields']) for t in (control, takeover)]
    if fields[0].keys() != fields[1].keys():
        raise ValueError('different field instrumentation')
    before, after = (t['graph_owned_teardown_bytes'] for t in (control, takeover))
    metrics = ['graph_owned_teardown_bytes', 'graph_unlisted_teardown_bytes',
               'retained_program_teardown_bytes', 'execution_and_takeover_peak_bytes',
               'max_takeover_extra_bytes', 'trace_buffer_bytes']
    return {
        'scope': 'actual standalone Cell runtime; requested heap, not RSS or timing',
        'program_sha256': control['program_sha256'],
        'final_state_sha256': control['final_state_sha256'],
        'runs': control['runs'],
        'final_state_matches_audit': True,
        'graph_saved_bytes': before - after,
        'graph_saved_percent': 100 * (before - after) / before,
        'lanes': [{**{k: t[k] for k in metrics}, 'mode': t['mode'],
                   'last_run_live_bytes': t['samples'][-1]['after'],
                   'peak_run': max(t['samples'], key=lambda s: max(s['execution_peak'], s['takeover_peak']))}
                  for t in (control, takeover)],
        'graph_fields': [{'field': k, 'control': fields[0][k], 'takeover': fields[1][k],
                          'saved': fields[0][k] - fields[1][k]}
                         for k in sorted(fields[0], key=fields[1].get, reverse=True)],
        'limitations': ['Graph teardown attributes shared allocations to their last owner',
                        'process peak includes compiled Program, Executor and fixed trace buffer',
                        'matching final state does not independently validate intermediate Runs',
                        'no additional RHS skipping is established by memory measurements'],
    }


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: analyze_owner_heap.py CONTROL TAKEOVER AUDITED_STORAGE OUTPUT')
    result = analyze(*(json.loads(Path(p).read_text()) for p in sys.argv[1:4]))
    Path(sys.argv[4]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('graph_saved_bytes', 'graph_saved_percent', 'runs')}))
