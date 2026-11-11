#!/usr/bin/env python3
"""Render the coverage manifest and paper table from the saved final audit."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('result',type=Path);a=p.parse_args()
d=json.loads(a.result.read_text());rows=d['cases'];counts=collections.Counter(r['status'] for r in rows)
for r in rows:
 if r['status']=='pass':
  folder=a.result.parent/Path(r['source']).stem
  files={'native':folder/'native.json','cell':folder/'run/state.json'}
  if all(p.exists() for p in files.values()):
   r['state_sha256']={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in files.items()}

assert sum(counts.values())==127
out=ROOT/'benchmarks/upstream-suite'
(out/'results.json').write_text(json.dumps(d,indent=2)+'\n')
with (out/'coverage.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['source','status','source_sha256','reason','cell_median_ms','native_schedule_seconds'])
 for r in rows:w.writerow([r['source'],r['status'],r['sha256'],r.get('reason',''),r.get('cell_bench',{}).get('median_ms',''),json.dumps(r.get('native_schedule_and_checks_seconds',[]))])
lines=[r'\subsection{Unmodified upstream compatibility audit}',
 r'We enumerate the 127 ordinary \code{.egg} inputs selected by the vendored CI benchmark, excluding its type-error and dedicated proof folders. Proof-testing variants and Rust API benchmarks remain separate. The external nightly input directory is absent. Each input retains its original bytes; no unsupported commands are stripped.',
 r'\begin{table}[ht]\centering\small\begin{tabular}{lr}\toprule Outcome & Inputs\\\midrule']
labels={'pass':'Exact final-state contract passed','unsupported':'Capability preflight rejected','compile_failed':'Full compilation/Bake failed','compile_timeout':'Compilation timed out','inconclusive':'Final-state proof inconclusive','difference':'Final-state difference','native_failed':'Native execution failed','runtime_failed':'Cell execution failed'}
for s,n in sorted(counts.items()):lines.append(f"{labels.get(s,s.replace('_',' '))} & {n}\\\\")
lines += [r'\bottomrule\end{tabular}\caption{Coverage of the unmodified upstream test inputs. Rejections and timeouts remain in the denominator.}\label{tab:upstream}\end{table}',
 r'The scalar implementation covers the vendored integer, float, string, boolean and Unit sort primitives; differential tests also exercise overflow, failed guards, NaN, signed zero and float-key collisions. Identity-order primitives, extension sorts, custom Rust primitives and broader source-command support remain outside this extension. Many upstream tests are rejected by the flat source-control interface rather than their arithmetic.',
 r'A pass requires successful source checks and an exact typed bijection of all original tables, scalar values, equality identities and visibility. Only compiler-generated tables are projected away. Unknown identities remain inconclusive. This final-state contract does not certify every unobserved Run boundary or proof generation. It applies no workload-specific algebraic or extraction-choice relaxation.',
 r'We save three timing samples for supported executions, with native schedule execution, native CI-style parse/execute/serialize time and Cell inference in distinct columns. Cell compilation/Bake and setup are separate. The small tests primarily establish coverage; their timing ratios are not presented as robust throughput gains. The complete manifest, executable hashes, samples and reasons are in \code{benchmarks/upstream-suite/}.']
(ROOT/'paper/upstream-results.tex').write_text('\n\n'.join(lines)+'\n')
print(dict(counts))
