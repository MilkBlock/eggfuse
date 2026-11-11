#!/usr/bin/env python3
"""Generate text tables from saved observations; never execute a workload."""
import argparse
import collections
import csv
import json
import math
from pathlib import Path
import statistics
ROOT = Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    rows=[json.loads(l) for l in (a.root/'suite.jsonl').read_text().splitlines()]
    ids=[(r['case'],r['pass_number']) for r in rows]
    assert len(set(ids))==len(ids),'duplicate samples'
    good=[r for r in rows if r['status']=='complete']
    result={'scope':'execution-time comparison; suite-wide native semantics not certified',
            'attempted':len(rows),'complete':len(good),'expected':288,
            'failures':[{'case':r['case'],'pass':r['pass_number'],'error':r.get('error','')} for r in rows if r['status']!='complete'],
            'phases':{}}
    for phase in (1,2,3):
        rs=[r for r in good if r['pass_number']==phase]
        native=sum(r['native_ms'] for r in rs)/1000;cell=sum(r['cell_ms'] for r in rs)/1000
        result['phases'][str(phase)]={'inputs':len(rs),'native_s':native,'cell_s':cell,
          'execution_time_ratio':native/cell if cell else None,
          'geomean':math.exp(sum(math.log(r['native_ms']/r['cell_ms']) for r in rs)/len(rs)) if rs else None,
          'prepare_s':sum(r['prepare_s'] for r in rs),
          'native_cli_s':sum(r['native_cli_ms'] for r in rs)/1000,
          'cell_cli_s':sum(r['cell_cli_ms'] for r in rs)/1000}
    totals=collections.defaultdict(list)
    for r in good:totals[r['case']].append(r)
    ratios=sorted(sum(x['native_ms'] for x in rs)/sum(x['cell_ms'] for x in rs) for rs in totals.values() if len(rs)==3)
    result['three_pass_cases']=len(ratios)
    if ratios:
        result['three_pass_ratios']={'min':min(ratios),'median':statistics.median(ratios),'max':max(ratios),
          'geomean':math.exp(sum(map(math.log,ratios))/len(ratios)), 'above_one':sum(x>1 for x in ratios)}
    result['selected']=[r for r in good if r['pass_number']==3 and any(n in r['case'] for n in ('raytrace','sum-bits'))]
    dest=ROOT/'benchmarks/eggcc-suite'
    (dest/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (dest/'benchmark.csv').open('w') as f:
        keys=['case','pass_number','status','native_ms','cell_ms','execution_time_ratio','prepare_s','native_cli_ms','cell_cli_ms','native_process_rss_bytes','cell_rss_through_inference_bytes','semantic_status']
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
    lines=[r'\subsection{Current eggcc replay}',
      r'The new replay uses the historical corpus of 96 workloads and three pass inputs, fixed common training, and a transferred donor. The standalone Cell implementation is based on revision \texttt{8450e627}; the native version-2.0 timing binary is built from the pristine \texttt{egglog-baseline} tag. Three fresh-process pairs alternate order for each input. Offline compilation/Bake and linking are recorded separately. The host is an Apple M3 Max with 48 GiB RAM; runtime and offline analysis each use one thread.',
      f'The campaign completed {len(good)} of {len(rows)} attempted pass inputs (288 expected).',
      r'\begin{table}[ht]\centering\small',
      r'\begin{tabular}{lrrrr}\toprule Input set & Native 2.0 (s) & Cell (s) & Ratio of sums & Geometric mean\\\midrule']
    for phase,x in result['phases'].items():
        ratio=x['execution_time_ratio']
        lines.append(f"Pass {phase} & {x['native_s']:.3f} & {x['cell_s']:.3f} & {ratio:.3f} & {x['geomean']:.3f}\\\\" if ratio is not None else f"{phase} & 0 & -- & -- & --\\\\")
    ns=sum(x['native_s'] for x in result['phases'].values());cs=sum(x['cell_s'] for x in result['phases'].values())
    if cs:lines.append(f'\\midrule All passes & {ns:.3f} & {cs:.3f} & {ns/cs:.3f} & {result["three_pass_ratios"]["geomean"]:.3f}\\\\')
    lines += [r'\bottomrule\end{tabular}',r'\caption{Current captured-pass execution times: sums of per-input medians. Ratios compare these executions; they are not suite-wide certified compiler speedups.}\label{tab:current-suite}\end{table}',
      f"Preparation totals {sum(x['prepare_s'] for x in result['phases'].values()):.2f} seconds. Native and Cell command-time sums are {sum(x['native_cli_s'] for x in result['phases'].values()):.3f} and {sum(x['cell_cli_s'] for x in result['phases'].values()):.3f} seconds; Cell additionally writes its graph and report.",
      r'As in the historical replay, native uses the default Rust allocator and Cell uses mimalloc. This is another implementation difference included in the aggregate timings. The Cell lane enables sparse storage, view ports and RSS measurement, with result-port repair and shared Entry publication. Repetitions must preserve its endpoint and ordered schedule digests. This proves repeatability, not equivalence to native egglog. The reviewed sum-bits choice contract passes separately; it is not extended to the other workloads. This replay does not execute the production extraction chain, and no suite-wide semantics-preserving acceleration is claimed.']
    for r in result['selected']:
        name=r['case'].replace('_',r'\_')
        lines.append(f"For \\texttt{{{name}}} Pass 3, native whole-process peak RSS is {r['native_process_rss_bytes']/2**20:.2f} MiB and Cell peak RSS through inference is {r['cell_rss_through_inference_bytes']/2**20:.2f} MiB. These are explicitly different windows.")
    if ratios:
        (ROOT/'paper/current-workloads.dat').write_text('rank ratio\n'+'\n'.join(f'{i+1} {v:.9f}' for i,v in enumerate(ratios))+'\n')
        lines += [r'\begin{figure}[ht]\centering\begin{tikzpicture}',
          r'\begin{axis}[width=0.87\linewidth,height=4cm,xlabel={Workload rank (three-pass totals)},ylabel={Native 2.0 time / Cell time},axis lines=left,ymajorgrids,tick label style={font=\footnotesize},label style={font=\small}]',
          r'\addplot[accent,thick,mark=*,mark size=0.75pt] table[x=rank,y=ratio]{current-workloads.dat};',
          r'\end{axis}\end{tikzpicture}',
          f'\\caption{{Current execution ratios for {len(ratios)} complete three-pass workloads, sorted. The geometric mean is {result["three_pass_ratios"]["geomean"]:.3f}. Semantic scope is the same as Table~\\ref{{tab:current-suite}}.}}\\label{{fig:current-dist}}\\end{{figure}}']
    (ROOT/'paper/eggcc-results.tex').write_text('\n\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='selected'},indent=2))

if __name__=='__main__':main()
