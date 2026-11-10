#!/usr/bin/env python3
"""Check saved receipt-frame compression runs; no workload/timing execution."""
import argparse
import json
from pathlib import Path
from check_links import load, sha
from check_mixed_outputs import pair


def check(args):
    result = pair(args.root, ('baseline', 'candidate'), args.program,
                  allowed={'/stage_spine/stats/effect_slots_initialized'}, charged=set())
    acceptance = load(args.root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['ordered_hashes']['state.json']
    before, after = result['changed_work']['/stage_spine/stats/effect_slots_initialized']
    assert after < before
    result.update(
        scope='standalone Cell CPU, normal sum-bits; work counts, not a speed benchmark',
        baseline_commit='39512f71 (same kernel as b840448c)',
        binaries={k: sha(getattr(args, k)) for k in ('baseline', 'candidate')},
        reports={k: sha(args.root / k / 'report.json') for k in ('baseline', 'candidate')},
        semantic_acceptance='pass',
        semantic_acceptance_sha256=sha(args.root / 'semantic-acceptance.json'),
        removed_slot_initializations=before-after,
        fraction_removed=(before-after)/before,
        live_obligations='Retained query-alias output slots, actual donors, non-elided raw results, '
                         'history absence, original publication ordering and visibility remain.',
        limits='This removes transient empty slots, not the shared operation descriptor array. '
               'No saved allocation, peak-memory reduction, eliminated publication or speedup is inferred. '
               'The publication work score is unchanged; do not count empty-slot savings as publication savings.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'program', 'baseline', 'candidate', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args), indent=2)+'\n')
