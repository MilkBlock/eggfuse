#!/usr/bin/env python3
"""Join the saved same-machine campaigns; preserve every measured time."""
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'benchmarks/egglog3-suite'
PAPER = ROOT / 'paper'


def read_rows(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    indexed = {(r['case'], r['pass_number']): r for r in rows}
    assert len(rows) == len(indexed) == 288
    assert all(r['status'] == 'complete' for r in rows)
    return indexed


def geomean(values):
    return math.exp(statistics.mean(map(math.log, values)))


def main():
    earlier = ROOT / 'benchmarks/eggcc-suite'
    a, b = read_rows(earlier / 'suite.jsonl'), read_rows(DEST / 'suite.jsonl')
    am, bm = (json.loads((d / 'metadata.json').read_text()) for d in (earlier, DEST))
    assert a.keys() == b.keys()
    assert am['binaries']['native'] == bm['binaries']['egglog2']
    assert am['capture_manifest_sha256'] == bm['capture_sha256']
    assert am['threads'] == bm['threads'] == 1
    assert am['repeats'] == bm['repeats'] == 3
    assert am['machine'] == bm['host']
    joined = []
    for key in sorted(a):
        old, new = a[key], b[key]
        assert old['flat_sha256'] == new['source_sha256']
        joined.append(dict(case=key[0], pass_number=key[1],
                           native2_a_s=old['native_ms'] / 1000,
                           native2_s=new['egglog2']['inference_ms'] / 1000,
                           native3_s=new['egglog3']['inference_ms'] / 1000,
                           eggfuse_s=old['cell_ms'] / 1000))
    fields = ('native2_a_s', 'native2_s', 'native3_s', 'eggfuse_s')
    groups = defaultdict(list)
    for row in joined:
        groups[row['case']].append(row)
    assert len(groups) == 96 and all(len(rows) == 3 for rows in groups.values())
    workloads = [dict(case=case, **{f: sum(r[f] for r in rows) for f in fields})
                 for case, rows in groups.items()]
    workloads.sort(key=lambda r: (r['native2_s'] / r['eggfuse_s'], r['case']))
    drift = [r['native2_s'] / r['native2_a_s'] for r in workloads]
    phases = {}
    for phase in (1, 2, 3, 'all'):
        rows = [r for r in joined if phase == 'all' or r['pass_number'] == phase]
        totals = {f: sum(r[f] for r in rows) for f in fields}
        totals.update(native2_over_eggfuse=totals['native2_s'] / totals['eggfuse_s'],
                      native3_over_eggfuse=totals['native3_s'] / totals['eggfuse_s'])
        phases[str(phase)] = totals
    summary = dict(
        sources=['benchmarks/eggcc-suite/suite.jsonl', 'benchmarks/egglog3-suite/suite.jsonl'],
        normalization='Common denominator for speed: batch B native2 time; no time rescaling or drift correction',
        batches={'A': ['native2 repeat', 'EggFuse'], 'B': ['native2 plotted baseline', 'native3']},
        inputs=len(joined), workloads=len(workloads), phases=phases,
        baseline_repeat=dict(aggregate_ratio=phases['all']['native2_s'] / phases['all']['native2_a_s'],
                             workload_median_ratio=statistics.median(drift),
                             workload_geomean_ratio=geomean(drift),
                             workload_min_ratio=min(drift), workload_max_ratio=max(drift)),
        workload_geomeans=dict(native2_over_eggfuse=geomean([r['native2_s'] / r['eggfuse_s'] for r in workloads]),
                                native3_over_eggfuse=geomean([r['native3_s'] / r['eggfuse_s'] for r in workloads])))
    (DEST / 'combined-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    with (DEST / 'combined-workloads.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=['rank', 'case', *fields], lineterminator='\n')
        writer.writeheader()
        writer.writerows(dict(rank=i, **row) for i, row in enumerate(workloads, 1))
    (PAPER / 'combined-workloads.dat').write_text('rank native2 native3 eggfuse\n' + ''.join(
        f"{i} 1 {r['native2_s'] / r['native3_s']:.9f} {r['native2_s'] / r['eggfuse_s']:.9f}\n"
        for i, r in enumerate(workloads, 1)))
    total = phases['all']
    (PAPER / 'combined-totals.dat').write_text('engine seconds\n' +
        f"2.0 {total['native2_s']:.9f}\n3.0 {total['native3_s']:.9f}\nEggFuse {total['eggfuse_s']:.9f}\n")
    lines = [r'\subsection{Combined eggcc comparison}',
        r'We compare EggFuse with native egglog 2.0 and 3.0 on the same 96 workloads and three captured compiler-pass inputs. All 288 inputs complete. Both campaigns use the same Apple M3 Max with 48 GiB RAM, one runtime thread, identical input bytes and timing boundaries, and medians of three fresh processes per input. Batch A alternates the version-2.0 baseline with EggFuse; batch B alternates the unchanged baseline executable with the upstream 3.0 release. Figure~\ref{fig:current-dist} and Table~\ref{tab:current-suite} combine the saved measurements directly.',
        r'The native baseline is \texttt{egglog-baseline} (\texttt{62ae6baa}, version 2.0.0); the 3.0 release is \texttt{v3.0.0} (\texttt{8879605c}). Only timing adapters are added, with the per-EGraph thread setter required by 3.0. EggFuse uses implementation \texttt{8450e627}, fixed common training and the historical donor. The native engines use the default Rust allocator; EggFuse uses mimalloc, sparse storage, view ports, result-port repair and shared Entry publication. These implementation differences are included in the comparison.',
        r'\begin{table}[ht]\centering\small',
        r'\begin{tabular}{lrrrrr}\toprule Input set & Native 2.0 (s) & Native 3.0 (s) & EggFuse (s) & 2.0 / EggFuse & 3.0 / EggFuse\\\midrule']
    for phase, totals in phases.items():
        label = r'\midrule All passes' if phase == 'all' else 'Pass ' + phase
        lines.append(f"{label} & {totals['native2_s']:.3f} & {totals['native3_s']:.3f} & {totals['eggfuse_s']:.3f} & {totals['native2_over_eggfuse']:.3f} & {totals['native3_over_eggfuse']:.3f}\\\\")
    lines += [r'\bottomrule\end{tabular}',
        r'\caption{Combined single-thread inference: sums of per-input medians. Native 2.0 and 3.0 are from batch B; EggFuse is from batch A. Offline preparation is excluded.}\label{tab:current-suite}\end{table}',
        r'\begin{figure}[ht]\centering\input{figures/combined}',
        r'\caption{Three engines on the same machine and inputs. Left: aggregate inference time (lower is better). Right: speed relative to the same batch-B native-2.0 denominator for each three-pass workload (higher is better). All series use the same workload order, sorted by EggFuse speed; the native-2.0 baseline is one. Measurements retain their original values across batches.}\label{fig:current-dist}\end{figure}',
        f"The unchanged native-2.0 binary totals {total['native2_a_s']:.3f} seconds in batch A and {total['native2_s']:.3f} seconds in batch B, a {(summary['baseline_repeat']['aggregate_ratio'] - 1) * 100:.2f}\\% difference. Its workload-level repeat ratio has median {statistics.median(drift):.3f} and range {min(drift):.3f}--{max(drift):.3f}. This repeat provides a check on cross-batch comparability; no correction factor is applied. Aggregate stability does not remove small-input timing variation.",
        f"EggFuse's aggregate execution-time ratios are {total['native2_over_eggfuse']:.3f} relative to native 2.0 and {total['native3_over_eggfuse']:.3f} relative to native 3.0. Giving each complete three-pass workload equal weight yields geometric means of {summary['workload_geomeans']['native2_over_eggfuse']:.3f} and {summary['workload_geomeans']['native3_over_eggfuse']:.3f}, respectively.",
        r'Offline EggFuse compilation/Bake and linking total 727.05 seconds. Inference starts after initialization and includes matching, RHS execution, completion and publication. The source schedules remain unchanged. Peak RSS on Raytrace Pass~3 is 459.09 MiB for the batch-A native process and 1776.66 MiB for EggFuse through inference; these remain different measurement windows.',
        r'These are execution comparisons, not suite-wide certified compiler speedups. Repeated EggFuse endpoints and schedule digests agree, and the reviewed sum-bits choice contract passes separately. Neither determinism nor source execution certifies native-version final-state equivalence or the production extraction chain. The native 3.0 release also changes relation representation and includes correctness fixes. Raw samples, source hashes and the join used for this figure are retained in \texttt{benchmarks/eggcc-suite/} and \texttt{benchmarks/egglog3-suite/}.']
    (PAPER / 'combined-results.tex').write_text('\n\n'.join(lines) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
