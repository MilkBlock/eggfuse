#!/usr/bin/env python3
"""Validate saved demand-projection executions, including new selection costs."""
import argparse
import json
from pathlib import Path
from check_links import load, sha, work
from check_mixed_outputs import pair
from check_view_query import stable

FIELDS = ('cell_query_witness_writes', 'cell_query_witness_checks', 'cell_query_witness_dispatches')
PATHS = {'/stage_spine/stats/'+k for k in FIELDS}


def check(args):
    # The control is 07c62ee5 plus the checked-in metering-only patch. Strip only
    # these new counters to verify its remaining normalized work against the
    # saved unmodified execution. Never impute missing work counters as zero.
    old, metered = [stable(work(load(p/'report.json'))) for p in
                    (args.unmetered, args.root/'baseline')]
    for key in FIELDS:
        assert key not in old['stage_spine']['stats']
        metered['stage_spine']['stats'].pop(key)
    for report in (old, metered):
        for key in ('peak_rss_through_setup_bytes', 'peak_rss_through_inference_bytes'):
            report.pop(key)
        for step in report['steps']:
            step.pop('phases')
    assert old == metered
    assert sha(args.unmetered/'state.json') == sha(args.root/'baseline/state.json')
    result = pair(args.root, ('baseline', 'candidate'), args.program,
                  allowed=PATHS, charged=PATHS)
    result['net_saved_witness_work'] = result.pop('publication_net_saved_operations')
    assert result['net_saved_witness_work'] > 0
    acceptance = load(args.root/'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['ordered_hashes']['state.json']
    result.update(
        scope='standalone Cell CPU, normal sum-bits; work counts, not a timing campaign',
        baseline_commit='07c62ee5 plus witness-projection-meter.patch',
        meter_patch_sha256=sha(Path(__file__).with_name('witness-projection-meter.patch')),
        binaries={k: sha(getattr(args, k)) for k in ('baseline', 'candidate')},
        semantic_acceptance='pass',
        semantic_acceptance_sha256=sha(args.root/'semantic-acceptance.json'),
        limits='Dispatches, single-atom comparisons and actual intermediate writes are charged once. '
               'No query, publication, repair or final required witness is removed. '
               'Equal-weight savings are not a speed estimate; monomorphized code-size costs are unmeasured.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'unmetered', 'program', 'baseline', 'candidate', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args), indent=2)+'\n')
