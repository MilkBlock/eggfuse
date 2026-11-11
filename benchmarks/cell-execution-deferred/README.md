# Prepare deferred Cell candidates in their existing worker batch

Scope: **standalone Cell CPU**, not native egglog. Control: `1a6de877`.
The full execution-ownership objective remains in the
[refactor checklist](../../docs/CELL_EXECUTION_REFACTOR.md).

The preceding complete runs retained 29 / 3,046 source-ordered worker segments
for sum-bits / Raytrace. Serial Spine candidates awaiting queries from the same
rule remained paired with Rc-backed Cursor objects in `deferred_queries`.
They could not join the already matched instances in the source Run's borrowed
worker batch. The shared typed execution plan already identifies input-derived
scalar operations; neither another binding nor another pool invocation is
needed to prepare them. Existing completed results can discharge later local
execution, but source effects and cross-Run publication obligations remain live.

Candidates now use the existing coordinator-owned Cursor arena from creation.
Their original Instance holds the move-only origin handle; the candidate also
retains source ordinal and depth. The candidate array is Send and is borrowed
directly into the same query invocation. Workers never read or update Cursor.
Selection still compares original inputs, descending depth and ascending source
ordinal. Losing origins are released immediately. Consuming an origin removes
only vacant trailing arena slots, preserving all other live handle addresses.
Query abort clears pending candidate origins as well as the query tasks.

This removes the separate serial ordinal vector, the zip/collect conversion
into deferred candidates, and the post-selection ordinal-stripping iterator.
Active deferred rule groups form a dense array with a rule-to-slot lookup;
preparation does not scan every possible rule. Instance values stay in their
existing owned Slots. Earlier Cursor storage and the active-group lookup are
new costs, not free memory savings.

## Complete work and semantic comparison

[results.json](results.json) is produced by [check.py](check.py) from saved
complete runs. Both programs and final-state exports match the control exactly;
all 1,428 / 16,883 ordered Run summaries and checked original graph, query and
maintenance counters agree. The reviewed native sum-bits acceptance is `pass`,
exit 0. Raytrace is a relative regression check, not a native equivalence proof.
These are work/semantic checks, not throughput or utilization measurements.

| Work / storage | sum-bits | Raytrace |
|---|---:|---:|
| Additional prepared and source-consumed operations | 29 | 4,283 |
| Added operations not consumed | 0 | 0 |
| Remaining later worker segments, before → after | 29 → 0 | 3,046 → 0 |
| Deferred instance groups / instances | 8 / 23 | 85 / 4,282 |
| Separate ordinal records, before → after | 321 → 0 | 25,119 → 0 |
| Deferred candidate conversion moves, before → after | 125 → 0 | 16,361 → 0 |
| Candidate header bytes, before → after | 216 → 144 | 216 → 144 |
| Cursor stores / losing origins released | 2,140 / 42 | 579,582 / 1,932 |
| Cursor arena capacity high-water bytes | 22,528 | 1,441,792 |
| Active-group capacity / rule-slot bytes | 768 / 4,656 | 768 / 4,656 |
| Borrowed-group cumulative capacity bytes, before → after | 9,216 → 11,680 | 86,272 → 112,960 |
| Preparation growth bytes, before → after | 11,184 → 11,880 | 1,037,832 → 1,140,624 |
| Later local-resumption growth bytes, before → after | 3,864 → 0 | 511,560 → 0 |

All new operations are consumed, but Raytrace retains the prior 336 unconsumed
query preparations. Added preparation exceeds removed resumption operations by
1,237 on Raytrace because not every RHS execution uses the optional resumption
loop. These are overlapping accounting views, not separate savings.

The candidate header no longer contains Cursor, which now resides in the arena;
the smaller header does not prove lower total memory. The new preparation also
increases slots present at winner sealing by 29 / 4,283, without a second array.
The old `batch_buffers` count falls by 504 / 7,548, but that counter includes
buffer categories even when empty and is not an exact allocation count. Added
rule eligibility checks are 252 / 3,774. No empty preparation chunks or worker
histogram heap allocations occur in these four-worker executions. Pending
groups and Cursor slots are zero after completion; retained capacities remain.

## Validation and reproduction

117 runtime unit tests and 46 selected forced-collision compiler integration
tests pass. The new ownership tests send the original candidate array through a
thread, compare winner order against source-order/stable-depth selection, check
loser release, and verify dense-group removal and abort with live origin handles.
Existing integration cases compare source Run states, real publication, foreign
constructor reuse, union, deletion/recreation, residual enumeration, early Hide
and failures at their original source positions. The all-feature runtime check
and README Cargo compile/run/bench commands pass; bench repeat 1 is a smoke check.

Use fresh output directories. Freeze the feature binary before README smoke
commands, which build the default runtime. Raw logs and exports are under
ignored `out/cell-execution-deferred`.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion --test parallel_residuals
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-deferred/check.py ROOT PRIOR_ROOT RESULTS.json
```

This checkpoint removes the remaining observed later scalar dispatch in these
workloads. It does not independently park effectful frames, move shared graph
effects to workers, complete all congruence locally, or unify every Cursor,
receipt and Entry lifetime. The graph's single `active_rhs` owner and synchronous
frontier executor remain the structural next boundary. Actual completed-apply
evidence should guide Bake toward compositions that eliminate shared-result
lookups and completion/publication handoffs within proven coverage. Larger
templates alone cannot remove source Run ordering or unknown external effects.
