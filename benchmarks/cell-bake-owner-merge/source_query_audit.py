"""Align source execution counts after removing generated marker maintenance.

This is scheduling/work evidence, not a per-Run graph-equivalence proof.
Usage: source_query_audit.py MARKED_MEMORY PLAIN_MEMORY REPORT
"""
import difflib
import json
from pathlib import Path
import sys


def align(marked, plain):
    # Exact reserved ruleset emitted by markers.rs, not a broad name prefix.
    maintenance = [s for s in marked if s['ruleset'] == 'cell-spine-complete']
    source = [s for s in marked if s['ruleset'] != 'cell-spine-complete']
    if any(s['ruleset'] == 'cell-spine-complete' for s in plain):
        raise ValueError('plain execution still contains generated maintenance')
    # Repeated saturation Runs may share a name. Include work counts so a
    # trailing idle iteration cannot displace its active predecessor.
    signature = lambda s: (s['ruleset'], s['logical_matches'], s['executed_bindings'])
    matcher = difflib.SequenceMatcher(a=list(map(signature, source)),
                                    b=list(map(signature, plain)), autojunk=False)
    idle, flags, matched = [], [], 0
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag == 'delete':
            for step in source[i:j]:
                if step['logical_matches'] or step['executed_bindings'] or step['changed']:
                    raise ValueError('removed source Run performed work')
                idle.append(step)
        elif tag == 'equal':
            for offset, (a, b) in enumerate(zip(source[i:j], plain[k:l])):
                if any(a[key] != b[key] for key in ('logical_matches', 'executed_bindings')):
                    raise ValueError('aligned source work differs')
                if a['changed'] != b['changed']:
                    flags.append(dict(marked_source_index=i+offset, plain_index=k+offset,
                                      ruleset=a['ruleset'], before=a['changed'], after=b['changed']))
                matched += 1
        else:
            raise ValueError('source Run order cannot be aligned by removing idle Runs')
    return dict(scope='source Run names and work counts; not graph-state or iteration-path equivalence',
                matched_source_runs=matched, removed_maintenance_runs=len(maintenance),
                removed_idle_source_runs=idle, changed_flag_differences=flags,
                source_logical_matches=sum(s['logical_matches'] for s in source),
                source_executed_bindings=sum(s['executed_bindings'] for s in source))


if __name__ == '__main__':
    marked, plain, output = map(Path, sys.argv[1:])
    result = align(json.loads(marked.read_text())['run_sequence'],
                   json.loads(plain.read_text())['run_sequence'])
    output.write_text(json.dumps(result, indent=2) + '\n')
