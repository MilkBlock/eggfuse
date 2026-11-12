# Actual results available before cross-Run constructor boundaries

This extends the bounded RHS observer on `ce65b9f6`, using the same derived
query-class program and sum-bits execution. It measures the actual standalone
Cell runtime, not native egglog. No execution takeover or compression is claimed.

The prior post-completion analysis could not tell whether a repeated constructor
already had a usable result before execution. This observer keys previously
returned receipts by actual table and arguments, then checks existing same-key
forwarding, liveness, table and visibility immediately before each generic
constructor boundary. It never guesses `(producer Cell, operation)` as an address.
The diagnostic map is bounded, retains no instances, and never affects execution.
It is not proposed as a production cache or additional maintained fact graph.

| Pre-boundary observation | Same Run | Cross Run |
| --- | ---: | ---: |
| Prior actual receipt visible | 698 | 1,074 |
| Previous execution did not retain receipt | 165 | 341 |
| Prior receipt hidden | 46 | 0 |

There are 4,068 observed boundaries, including 1,744 first observations. All
1,772 visible-prior boundaries complete with zero newly created facts. None
requires transient receipt forwarding in this sample. This scope differs from
the earlier 197 whole-input repeat candidates: constructor argument projection
also discovers reuse between different rules and different whole-Cell inputs.
Keys are not re-canonicalized when unions occur, so this undercounts candidates.

Join observations back to completed Cells and require every distinct constructor
site to have a successful visible predecessor. **632 Cells** meet that condition,
including **406 with a cross-Run predecessor**. These still perform 632 and 406
constructor requests respectively; none creates facts, updates or union requests.
Thus this is not merely recounting operations already eliminated by handoff.
The leading cross-Run complete-Cell rules are 424 (79), 518 (75), 58 (48),
122 (38), 523 (31), 522 (27), and 486 (18).

Each site is checked when reached, **not all at Cell entry**. Visibility alone
does not discharge query/delta ownership, publication, later history exports or
source-frame users. Nor does a previous receipt imply an existing static Entry
route: several observed producer/consumer pairs cross rule identities. The next
Bake step must project these donors through actual matched Cell Entries, prove
result coverage at the scheduled switch, and remove the covered query/RHS/handoff
rather than install this diagnostic hash map in production. Missing receipts
should only be retained when the resulting static consumer coverage pays for it.

The 46 hidden same-Run predecessors demonstrate why a previous successful
constructor call alone is not a reusable saturation certificate.

All 1,428 saved Run graph and ordered RHS/write/resume hashes match. Program,
final graph, mutation/request counters and source storage equal the unobserved
control. Observation adds 994 stable-node lookups, 992 port reads/root resolutions
and 1,076 root-parent probes; diagnostic memory/time are not compression savings.
The final graph exactly equals the saved semantic export; choice diagnosis passes.
Tests cover bounded observation and four offline cases including missing/retired
receipts, mutations, failed executions, incomplete archives, and duplicate sites.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/rhs-before-audit.json --natural --shared-owners --parent-takeover --port-domains-only --rhs-projection-trace
python3 benchmarks/cell-structural-compression/analyze_rhs_before.py out/cell-structural-compression/rhs-before-audit.json benchmarks/cell-structural-compression/rhs-before-results.json out/cell-structural-compression/domain-classes-derived-audit.json
python3 benchmarks/cell-structural-compression/test_rhs_before.py
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/rhs-before-semantic.json
```
