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
    storage = after.pop('table_lists')
    assert before == after, 'every serialized prediction and closure signature must agree'
    plan = before['plan']
    previous = before['storage']
    extra = plan['completion_reads'] + list(plan['query_demands'].values())
    extra += [scope['tables'] for scope in plan['rulesets'].values()]
    old_bytes = previous['shared_payload_and_rc_bytes'] + previous['shared_handles_bytes']
    old_bytes += len(extra)*24 + sum(map(len, extra))*8
    new_bytes = storage['shared_payload_and_rc_bytes'] + storage['handles_bytes']
    assert new_bytes < old_bytes
    runtime = pair(args.root, ('baseline', 'candidate'), args.program, allowed=set(), charged=set())
    acceptance = load(args.root/'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == runtime['ordered_hashes']['state.json']
    return dict(scope='standalone Cell CPU optional completion prediction; retained table-list storage',
        baseline_commit='d13227b7', program=before['program'], closure_sha256=before['closure_sha256'],
        exact_plan_and_closure_equal=True, storage=storage,
        baseline_bytes=old_bytes, candidate_bytes=new_bytes, bytes_saved=old_bytes-new_bytes,
        fractional_reduction=1-new_bytes/old_bytes,
        runtime=runtime, semantic_acceptance='pass',
        binaries={k: sha(getattr(args,k)) for k in ('baseline','candidate')},
        inspection_sha256={'before':sha(args.before),'after':sha(args.after)},
        limits='64-bit model: previous nonshared Vec headers 24 bytes and exact-length payload; '
               'Rc headers estimated as two words. Includes all table-list handles, excludes outer '
               'container headers, allocator rounding, temporary construction and unrelated storage. '
               'No latency, whole-process RSS or new cross-Run takeover claim.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('before','after','root','program','baseline','candidate','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    args.output.write_text(json.dumps(check(args),indent=2)+'\n')
