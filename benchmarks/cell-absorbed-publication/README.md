# Absorbed root Cells publish through the final Entry slot

Control: `9b1844ae`. This is the **standalone Cell CPU**, not native egglog.
Work and allocation checks below establish a publication takeover, not a
throughput improvement or a general sparsity theorem. No new timing campaign
has been run for this change.

## Opportunity and proof

The last actual-execution census found 957,754 Get/Expr-size matches and only
250,442 effective updates. In the sampled hot windows, changed scalar inputs
usually explain repeated matching; an ordinary completed-state cache cannot
skip them. The next useful Bake candidate is a scalar absorption condition,
with source publication and lifetime obligations explicitly retained.

One obligation was unnecessarily represented by a complete pending Cell even
after a single scalar write returned an unchanged, existing function result.
For a fresh root with no requested history, the final Entry only needs that
actual result and the new root's source identity. Retaining the old publication
would be wrong: a different producer may have written earlier, and source
order still decides the continuation supplied to a later query.

This change stages that **new** root directly in the Entry's existing source
slot. It deletes the corresponding `Completion`, generic output registration,
inline-result storage and later Completion traversal. A 24-byte temporary record
retains the actual function index, Entry slot and root identity for repair.
There is no second binding copy, consumer list, or runtime fact graph.

Admission derives from the existing single-write instruction and shared Cell
outputs: exactly one permanent, Entry-owned result; no output alias; actual
write unchanged; `Started::Root`; no catalog or training root state. Live
continuations, demanded history, visibility-changing tables, receipt auditing
and scoped completion retain the original path.

The runtime still performs matching and the scalar write/merge. This does
**not** yet prove absorption before query expansion, skip a logical match, or
eliminate constructor/function lookup. It makes the publication obligation
cheaper before attempting that larger takeover.

## Visibility and order

Workers and all source-Run queries have finished before staging begins. Only
the coordinator's exclusive RHS phase can use the path. It changes source
metadata, not query row values. A query cannot start before global repair and
publication finish; scoped/deferred completion is excluded.

After repair, staged results follow the same actual receipt forwarding and
visibility checks. Ordinary completions may still supersede them. The final
Entry preserves the last source, including when distinct function keys merge.
Fresh roots keep their original ID, epoch, stage and output position; historical
cursors already held by matched instances keep their own ownership.

Source order uses existing pending-Cell positions and monotone root identities:
normal completions occupy odd positions; roots between them occupy the preceding
even position and compare their root IDs. The global base advances only when
the pending arena drains. This replaces the old publication-batch stamp without
widening Entry slots or adding an order field to every Completion. Remaining
Completions stay **104 bytes**, publication slots stay **64 bytes**.

An initial prototype added a per-Completion order field and increased requested
bytes. That version was replaced before admission; its ignored artifacts remain
under `out/cell-absorbed-publication/*-prototype` for diagnosis.

## Actual work, including the new costs

| Work | sum-bits | Raytrace first 1,280 Runs | Complete Raytrace |
|---|---:|---:|---:|
| Completion records and visits removed | 228 | 5,654 | 834,716 |
| New admission checks | 291 | 6,035 | see results.json |
| New temporary records and repair checks | 228 | 5,654 | 834,716 |
| Staged sources that win final publication | 223 | 5,145 | 449,733 |
| Additional Entry slot writes | 5 | 511 | 384,985 |
| Additional Entry probes for forwarding | 0 | 2 | 2 |
| Retained temporary-vector capacity | 384 B | 24,576 B | 196,608 B |

Complete Raytrace captures 2,748,979 → 1,914,263 ordinary pending contexts and
visits 2,737,962 → 1,903,246 Completions. These are two observations of the same
834,716 takeovers, not independent savings to add together. Final anchor
publications remain 2,126,781, resumed steps 577,650, history capture reads
9,602, and table queries 2,584,660.

Staging performs some source-slot writes that later lose to another source.
They are charged rather than hidden by the lower number of Completion records.
It must check staged records and order all candidates; this is not free
publication or removal of repair. It remains possible for the new work to
offset the deleted work in elapsed time.

Allocator-instrumented short executions:

| Requests, before → after | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Allocation calls | 81,033 → 81,034 | 2,325,463 → 2,325,464 |
| Reallocation calls | 13,474 → 13,476 | 343,478 → 343,486 |
| Cumulative requested bytes | 19,574,867 → 19,575,539 | 960,887,228 → 960,936,284 |

The additions reconcile with growth of the new temporary vector. These are
cumulative requests, not RSS or traffic measurements. No full-Raytrace
allocation measurement or throughput improvement is claimed here.

## Validation

- 97 runtime unit tests and 59 compiler integration tests pass, including
  query workers, scoped completion, inherited state and Ripsat completion.
- The new native-checked fixture interleaves unchanged roots with earlier and
  later changed writers, key coalescence and late input changes. It exercises
  staged winners, losers and receipt forwarding, comparing every Run's graph,
  bindings, ordered mutation and resume digests with the legacy source path.
- Frozen sum-bits and Raytrace-prefix states, all ordered Run records, actual
  graph operation counts and query counts are exact against the prior branch.
  The unchanged sum-bits choice validator returns `pass` / exit 0 on the new
  state and saved native exports.
- Complete Raytrace has the identical final state digest, all 16,883 Run records,
  graph counters, per-rule census and query count. Fourteen hot windows also
  retain exact ordered binding/write/resume digests. This is relative Raytrace
  evidence, not a new independent native proof or every-Run graph export.
- Minimal and all-feature compilation and the README compile/run/bench commands
  pass. Bench repeat 1 is a smoke check only.

## Reproduction

Use the cell-fixed-reads frozen programs and fresh output directories. The short
control uses the `991896e8` frozen prefix: `9b1844ae` only added inactive audit
code. Complete and window controls are the saved cell-change-locality results.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,allocation-metrics --example query_prefix
PREFIX SUM_PROGRAM ROOT/sum 2000 4 64 canonical --repair-ports --entry-publications
PREFIX RAY_PROGRAM ROOT/ray1280 1280 4 64 canonical --repair-ports --entry-publications
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,slot-transfer-audit --example cell_change_windows
OBSERVER RAY_PROGRAM benchmarks/cell-change-locality/windows.json ROOT/ray-audit control
OBSERVER RAY_PROGRAM benchmarks/cell-change-locality/windows.json ROOT/census census
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-absorbed-publication/collect.py ROOT RESULTS.json
```

The collector expects frozen binaries named `before-prefix`, `prefix` and
`observer` in ROOT; it hashes them and the evidence. The semantic directory uses
the documented unchanged native inputs and the candidate `run-values/state.json`.
No generated binaries or raw graph exports are tracked.
