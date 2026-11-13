# View8 cross-Run handoff evidence

This is the actual standalone Cell executor, not native egglog or a synthetic
model. It adds a diagnostic example and offline analysis; no runtime takeover
is implemented and no memory or speed improvement is claimed.

## Finding

The saved cursor history alone misses a useful structural relationship:
rule 507 has 102 completion events, all with no cursor parent. The new observation
captures the actual winner inputs and the visible View8 rows before each Run.
Exact-value matching recovers 98 prior-Run producer events:

| Producer | Consumer matches | Run gap |
| --- | ---: | ---: |
| 286, completion query | 50 | 6–9 |
| 502, Const extraction | 5 | 6–10 |
| 504, Get extraction | 14 | 6 |
| 505, Single extraction | 29 | 6–10 |

All 102 matches already have partial query continuation (`[1,true]`), but none
has a direct iterative token. Do not interpret missing history parents as
absence of all query reuse. The missing relationship is between the matched
View row's actual producer and the consumer's completed state.

Four remaining consumer matches have valid visible row origins but no matching
completion event. Effective write observations identify their sources as rule
503: source Cells 2212, 2213, 2214 (Run 255) and 4230 (Run 651). The report leaves
these four links unresolved rather than inventing completion events. Even a
history with zero dropped events does not cover all source applications: some
executions do not enter the installed continuation catalog. Iterative learning
must also consider actual writes from these sources.

## What can and cannot be inherited

View8 carries `PotentialExtractedExpr(expr,pair)=potential` and
`TCPair(term,cost)=pair`. Its original completion rule establishes both from
constructor query facts. Other producers establish them through completed
constructors before publishing the View.

Consumer 507 additionally reads the CURRENT `ExtractedExpr(expr)` result,
queries its `TCPair(old_term,old_cost)` and checks `cost < old_cost`. Those facts
are not established by the View producer. Consumer 508 checks negative cost
and panics; it must not disappear merely because this trace never triggered it.

Therefore a future combined Cell should inherit the candidate tuple and actual
pair witness, then execute the mutable read and scalar comparison at the
original consumer Run. It cannot jump unconditionally to a saturated RHS.
The `TCPair(term,cost)` RHS can potentially use that inherited actual witness,
but all producers must be checked, and liveness/equality/visibility preserved.
Current `known_results` has no plan for rule 507. This is a specific compiler
proof opportunity, not evidence that every query or publication can be skipped.

The observations contain 454 source Set positions to View8 among selected
matches, versus 192 effective writes. Rule 286 accounts for 193 positions and
65 writes; rule 507 has 102 positions and zero writes. These positions are not
committed mutations or newly saved operations; existing execution shortcuts may
already avoid work. No consumer can remove the materialized table until it
covers completion-rule sources, residual matching, and union-enabled matches.

## Validation and reproduction

The trace uses `closure-existing/program.json`, whose recipe equals the current
`domain-classes-derived` recipe, but whose catalog/runtime lane is the historical
observation control. Do not combine its counts with the current compression
lane as if measured in the same execution.

All 1,428 saved per-Run graph and ordered RHS/write/resume hashes agree. The
final export exactly equals the saved CPU semantic export, and the existing
choice-diagnosis gate passes (recorded in `view8-handoff-semantic.json`). Three
analyzer regressions cover root provenance, missing/unequal input refusal, and
archive/future-origin rejection. No new runtime scheduling behavior is enabled.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_handoff_trace -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json CellSpineView8 out/cell-structural-compression/view8-handoff-trace.json
python3 benchmarks/cell-structural-compression/analyze_handoff_trace.py out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/view8-handoff-trace.json benchmarks/cell-structural-compression/view8-handoff-results.json
python3 -m unittest discover -s benchmarks/cell-structural-compression -p test_handoff_trace.py
```

Raw bindings and snapshots are generated under `out/`, not checked in. The
tracked report includes their hash, exact producer links, residual typed query
atoms and unresolved sources, so subsequent Bake changes have specific inputs
and obligations rather than only a ruleset-frequency histogram.
