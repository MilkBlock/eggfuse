#!/usr/bin/env python3
"""Summarize saved native-version pairs without running any workload."""
import argparse
import collections
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def geometric(values):
    return math.exp(sum(map(math.log, values)) / len(values)) if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'benchmarks/egglog3-suite')
    parser.add_argument('--paper', action='store_true', help='Generate the completed campaign manuscript table')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.input.read_text().splitlines()]
    assert len({(r['case'], r['pass_number']) for r in rows}) == len(rows)
    good = [r for r in rows if r['status'] == 'complete']
    result = {'attempted': len(rows), 'complete': len(good), 'expected': 288,
              'ratio_definition': 'egglog2 / egglog3; above one favors egglog3',
              'failures': [r for r in rows if r['status'] != 'complete'], 'phases': {}}
    for phase in (1, 2, 3, 'all'):
        items = [r for r in good if phase == 'all' or r['pass_number'] == phase]
        sums = {arm: {key.removesuffix('_ms') + '_s': sum(r[arm][key] for r in items) / 1000
                      for key in ('inference_ms', 'search_apply_ms', 'merge_ms', 'rebuild_ms', 'cli_ms')}
                for arm in ('egglog2', 'egglog3')}
        ratio = sums['egglog2']['inference_s'] / sums['egglog3']['inference_s'] if items else None
        result['phases'][str(phase)] = {'inputs': len(items), 'totals_seconds': sums,
                                       'ratio_of_sums': ratio, 'per_input_geomean': geometric([r['egglog2_over_3'] for r in items])}
    grouped = collections.defaultdict(list)
    for r in good:
        grouped[r['case']].append(r)
    ratios = [sum(r['egglog2']['inference_ms'] for r in group) / sum(r['egglog3']['inference_ms'] for r in group)
              for group in grouped.values() if len(group) == 3]
    result['three_pass_workloads'] = {'count': len(ratios), 'geomean': geometric(ratios),
                                     'egglog3_faster': sum(r > 1 for r in ratios),
                                     'egglog3_slower': sum(r < 1 for r in ratios)}
    result['selected'] = [r for r in good if any(x in r['case'] for x in ('sum-bits', 'raytrace'))]
    historical = {(r['case'], r['pass_number']): r for r in map(json.loads, (ROOT / 'benchmarks/eggcc-suite/suite.jsonl').read_text().splitlines())}
    shared = [r for r in good if (r['case'], r['pass_number']) in historical]
    for row in shared:
        assert historical[row['case'], row['pass_number']]['flat_sha256'] == row['source_sha256']
    old2 = sum(historical[r['case'], r['pass_number']]['native_ms'] for r in shared)
    old_cell = sum(historical[r['case'], r['pass_number']]['cell_ms'] for r in shared)
    new2 = sum(r['egglog2']['inference_ms'] for r in shared)
    new3 = sum(r['egglog3']['inference_ms'] for r in shared)
    result['earlier_campaign_reference'] = {'warning': 'Cell was not rerun in these pairs; ratios cross measurement campaigns',
        'matched_inputs': len(shared), 'earlier_native2_s': old2 / 1000, 'earlier_cell_s': old_cell / 1000,
        'current_native2_s': new2 / 1000, 'current_native3_s': new3 / 1000,
        'native2_current_over_earlier': new2 / old2 if old2 else None,
        'native3_over_earlier_cell': new3 / old_cell if old_cell else None}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    markdown = ['# Saved native-version comparison', '',
                f"Completed {len(good)} / {len(rows)} attempted inputs; full corpus: 288.", '',
                '| Inputs | Native 2.0 (s) | Native 3.0 (s) | 2.0 / 3.0 |',
                '|---|---:|---:|---:|']
    for phase, values in result['phases'].items():
        if not values['inputs']:
            continue
        times = values['totals_seconds']
        markdown.append(f"| {phase} | {times['egglog2']['inference_s']:.3f} | {times['egglog3']['inference_s']:.3f} | {values['ratio_of_sums']:.3f} |")
    if ratios:
        markdown += ['', f"Three-pass workload geometric mean (2.0 / 3.0): **{geometric(ratios):.3f}**. "
                     f"3.0 is faster on {sum(r > 1 for r in ratios)} / {len(ratios)} workload totals.",
                     'Small differences are observations, not claims of statistical significance.']
    markdown += ['', '| Workload | Pass | Native 2.0 (ms) | Native 3.0 (ms) | 2.0 / 3.0 |',
                 '|---|---:|---:|---:|---:|']
    for row in result['selected']:
        markdown.append(f"| {row['case']} | {row['pass_number']} | {row['egglog2']['inference_ms']:.3f} | {row['egglog3']['inference_ms']:.3f} | {row['egglog2_over_3']:.3f} |")
    if shared:
        markdown += ['', f"For these {len(shared)} inputs, the unchanged native-2.0 binary's total is "
                     f"{new2 / old2:.3f} times the earlier campaign total. Earlier Cell inference was "
                     f"{old_cell / 1000:.3f} s. Current 3.0 / earlier Cell is {new3 / old_cell:.3f}; "
                     '**this crosses campaigns and is not a paired 3.0/Cell measurement**.', '',
                     'Timing success does not certify final-state or extracted-program equivalence. '
                     'See README.md for version, allocator and timing boundaries.']
    (args.output / 'results.md').write_text('\n'.join(markdown) + '\n')
    with (args.output / 'comparison.csv').open('w') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['case', 'pass', 'status', 'egglog2_ms', 'egglog3_ms', 'egglog2_over_3'])
        for r in rows:
            writer.writerow([r['case'], r['pass_number'], r['status'],
                             r.get('egglog2', {}).get('inference_ms'),
                             r.get('egglog3', {}).get('inference_ms'), r.get('egglog2_over_3')])
    if args.paper:
        assert len(rows) == 288 and len(good) == 288, 'Report incomplete campaigns explicitly before generating a timing table'
        lines = [r'\subsection{Native egglog 3.0 comparison}',
            r'We additionally compare the unchanged version-2.0 baseline binary with the upstream \texttt{v3.0.0} release (\texttt{8879605c}). Both native engines execute the same original captured sources, using one thread, ordinary release builds and the default Rust allocator. Three fresh-process pairs alternate order per input. The 3.0 timing adapter only changes the thread setter to its per-EGraph API; no kernel changes are applied. All 288 inputs complete. Table~\ref{tab:native-three} reports this new paired campaign; its 2.0 measurements are not copied from Table~\ref{tab:current-suite}.',
            r'\begin{table}[ht]\centering\small',
            r'\begin{tabular}{lrrr}\toprule Input set & Native 2.0 (s) & Native 3.0 (s) & 2.0 / 3.0\\\midrule']
        for phase, values in result['phases'].items():
            times = values['totals_seconds']
            label = 'All passes' if phase == 'all' else 'Pass ' + phase
            lines.append(f"{label} & {times['egglog2']['inference_s']:.3f} & {times['egglog3']['inference_s']:.3f} & {values['ratio_of_sums']:.3f}\\\\")
        lines += [r'\bottomrule\end{tabular}',
            r'\caption{Native version comparison: sums of per-input median inference times. A ratio above one favors 3.0.}\label{tab:native-three}\end{table}',
            f"For complete three-pass workloads, the geometric mean of the 2.0/3.0 ratios is {geometric(ratios):.3f}; 3.0 is faster on {sum(r > 1 for r in ratios)} of {len(ratios)} workload totals. These measurements retain small regressions as well as improvements.",
            r'The earlier Cell measurements are a separate campaign, not an interleaved Cell/3.0 comparison. Successful source execution does not certify native-version final-state equivalence. Release 3.0 changes relations to constructors and includes correctness changes, so lower time cannot be attributed exclusively to faster evaluation of identical logical work. The complete records and timing adapter are in \texttt{benchmarks/egglog3-suite/}.']
        (ROOT / 'paper/egglog3-results.tex').write_text('\n\n'.join(lines) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('selected', 'failures')}, indent=2))


if __name__ == '__main__':
    main()
