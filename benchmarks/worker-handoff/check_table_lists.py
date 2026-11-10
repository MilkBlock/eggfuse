#!/usr/bin/env python3
"""Check exact prediction sharing and saved scoped-runtime results; no reruns."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'cell-unification'))
from check_links import load, sha
from check_mixed_outputs import pair


def check(args):
    before, after = load(args.before), load(args.after)
    storage = after.pop('table_lists' if args.mode in ('tables','hybrid') else 'scope_masks')
    previous_storage = None
    if args.mode == 'hybrid':
        previous_storage = before.pop('table_lists')
        old_demands,new_demands=before.pop('storage'),after.pop('storage')
        for key in ('lists','unique_lists','unshared_payload_bytes'):
            assert old_demands[key]==new_demands[key]
        for key in ('lists','logical_values','unique_lists'):
            assert previous_storage[key]==storage[key]
    assert before == after, 'every serialized prediction and closure signature must agree'
    if args.mode == 'hybrid':
        old_bytes=previous_storage['shared_payload_and_rc_bytes']+previous_storage['handles_bytes']
        new_bytes=storage['shared_payload_and_rc_bytes']+storage['handles_bytes']
    elif args.mode == 'tables':
        plan = before['plan']
        previous = before['storage']
        extra = plan['completion_reads'] + list(plan['query_demands'].values())
        extra += [scope['tables'] for scope in plan['rulesets'].values()]
        old_bytes = previous['shared_payload_and_rc_bytes'] + previous['shared_handles_bytes']
        old_bytes += len(extra)*24 + sum(map(len, extra))*8
        new_bytes = storage['shared_payload_and_rc_bytes'] + storage['handles_bytes']
    else:
        old_bytes = storage['old_boolean_payload_bytes'] + storage['scopes']*24
        new_bytes = storage['packed_payload_bytes'] + storage['descriptor_bytes']
    allocation_model = None
    if args.mode == 'hybrid':
        plan=before['plan']
        rows=plan['completion_reads']+list(plan['query_demands'].values())
        rows += [scope['tables'] for scope in plan['rulesets'].values()]
        rows += [rule[k] for rule in plan['rule_demands'] for k in ('query','rhs','accesses')]
        unique=set(map(tuple,rows))
        allocation_model=dict(baseline_retained_blocks=len(unique),
            candidate_retained_blocks=len(unique)+sum(bool(row) for row in unique),
            scope='Source-layout count: one Rc block per unique set, plus one nonempty boxed payload in hybrid. Not allocator-event instrumentation; excludes temporary interning and allocator rounding.')
    assert new_bytes < old_bytes
    runtime = pair(args.root, ('baseline', 'candidate'), args.program, allowed=set(), charged=set())
    acceptance = load(args.root/'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == runtime['ordered_hashes']['state.json']
    return dict(scope='standalone Cell CPU optional completion prediction; retained '+args.mode+' storage',
        baseline_commit={'tables':'d13227b7','masks':'d3c12092','hybrid':'9cc5437f'}[args.mode], program=before['program'], closure_sha256=before['closure_sha256'],
        exact_plan_and_closure_equal=True, storage=storage, allocation_model=allocation_model,
        baseline_bytes=old_bytes, candidate_bytes=new_bytes, bytes_saved=old_bytes-new_bytes,
        fractional_reduction=1-new_bytes/old_bytes,
        runtime=runtime, semantic_acceptance='pass',
        binaries={k: sha(getattr(args,k)) for k in ('baseline','candidate')},
        inspection_sha256={'before':sha(args.before),'after':sha(args.after)},
        limits=('Hybrid counts shared objects, encoding descriptors, payloads, two-word Rc headers and all handles. '
                'Excludes allocator rounding, compiler temporaries and unrelated plan storage. '
                'No speed or new takeover claim.' if args.mode=='hybrid' else '64-bit model: previous nonshared Vec headers 24 bytes and exact-length payload. '
                + ('Rc headers estimated as two words; includes all table-list handles. ' if args.mode == 'tables'
                   else 'Includes 24-byte mask descriptors; words are boxed with exact capacity. ')
                + 'Excludes outer container headers, allocator rounding, temporary construction and unrelated storage. '
                  'No latency, whole-process RSS or new cross-Run takeover claim.'))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('before','after','root','program','baseline','candidate','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--mode',choices=('tables','masks','hybrid'),default='tables')
    args=parser.parse_args()
    args.output.write_text(json.dumps(check(args),indent=2)+'\n')
