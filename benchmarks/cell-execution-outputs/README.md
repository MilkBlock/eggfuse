# Independent Cell execution and publication results

Scope: **standalone Cell CPU**, not native egglog. Control: `3ace9e35`.
The complete objective remains in [the execution refactor](../../docs/CELL_EXECUTION_REFACTOR.md).

The preceding complete executions already consumed the observed later scalar
preparations without worker round trips. They still borrowed the shared pending
publication arena 3,957 / 699,784 times on sum-bits / Raytrace. Even an execution
that might stop at a shared-effect boundary temporarily owned other completed
Cells' results. Joint history/publication frames had already removed this
dependency; ordinary frames had not.

The typed `EffectPlan` already gives each operation's result slot, the retained
output prefix, exact alias donors and the transient suffix. These facts prove
that an executing Cell needs only its own results. Execution now borrows an
empty buffer, fills that same layout, and moves the retained array into its
owning Completion. Entry publication reads this original array. The global
output arena, offsets and offset additions on receipt access are removed.
There is no per-output copy, extra binding, effect replay log or consumer list.

Partial publication retains the Cell's buffer until its remaining tables become
ready. Abort recycles only the interrupted Cell's buffer. Empty buffers are
pooled after completion or publication, retaining capacity across source Runs.
Joint history results and allocation-free inline function delivery keep their
existing storage. Ordinary history capture is still separate; this change does
not claim complete history/publication unification.

The source scheduler, actual foreign constructor witnesses, receipt forwarding,
deletion checks, winner order and completion/publication boundaries remain
authoritative. The graph's single active RHS and apply-scoped ownership Entry
context still need work before independent parked execution is enabled.

## Costs and acceptance

[results.json](results.json) records complete four-worker, grain-1 executions.
Final exports are byte-identical and all 1,428 / 16,883 ordered Run summaries
match. Checked graph, query, RHS, history and publication work is unchanged.
Native sum-bits acceptance is `pass`, exit 0. These are work/semantic results.

| Ownership / cumulative capacity | sum-bits | Raytrace |
|---|---:|---:|
| Shared publication-arena borrows, before → after | 3,957 → 0 | 699,784 → 0 |
| Original arrays moved into publication | 3,416 | 652,828 |
| Buffer takes / returns | 4,372 / 4,317 | 742,571 / 738,267 |
| Buffer capacity growth events | 128 | 39,489 |
| Added buffer capacity bytes, retained in pool at end | 9,520 | 2,742,768 |
| Pool header capacity bytes | 3,072 | 1,572,864 |
| Retained empty buffers at end | 121 | 39,067 |
| Completion header bytes, before → after | 104 → 120 | 104 → 120 |
| RHS continuation header bytes, before → after | 448 → 440 | 448 → 440 |

Buffers of zero capacity need no return to the pool. Output-array moves change
ownership only; existing result-copy counts are unchanged. The pool is empty
of facts, but retains allocation capacity. These costs preclude interpreting
arena-borrow elimination as a memory reduction or a throughput result.

`owned-cell-outputs/v2` reports pool takes/returns, capacity growth events/bytes,
pool-header growth, result-buffer ownership moves, retained pool capacity and
Completion record capacity. These are not complete allocator measurements or
peak process memory. The larger owning Completion header is charged separately;
removing shared-arena borrowing does not itself demonstrate a speedup.

Iterative Bake's measured-work reader explicitly accepts this version and
charges takes, returns, growth events and ownership transfers. Coverage, reuse
subsets and capacity bytes do not earn a second operation credit. New reports
missing these costs fail validation; historical span reports retain their
original interpretation. The operation score remains uncalibrated.

The broader compiler unit check also exposed the pre-existing reader's rejection
of current `cell-run/v5` worker reports. The reader now preserves v4 task costs
and includes v5 matched/deferred admission, grouping, scratch growth and total
preparation. Nested matched/deferred preparation and later-operation subsets are
not charged twice. Missing current fields fail; historical versions keep their
original interpretation. This makes current worker reports usable by iterative
Bake rather than silently omitting their preparation costs.

The historical `peak_cell_output_slots` report now bounds pending receipts at
delivery installation instead of the old append-only arena span. It is recorded
as a changed storage counter, not compared as an equal-work or memory-saving
measurement. Exact logical graph/query/RHS/publication work is checked separately.

The ownership unit test holds two ordinary effect frames simultaneously, moves
the first array into delivery at the same address, aborts the second, reuses its
empty buffer and keeps a partially published first result intact. Integration
checks exercise real Entry publication, alias donors, retained partial outputs,
foreign results, union, deletion/recreation and source-Run visibility. The
required sum-bits native choice contract is checked from saved exports. Raytrace
state and ordered Run checks are relative regression evidence.

## Reproduction

121 runtime unit tests, 15 compiler unit tests and 74 selected integration tests
pass. The compiler/integration run forces hash and Sieve collisions. Runtime
unit tests use normal hashes. The two earlier rejected runs are retained in
the raw output directory: one exposed the new output-version reader gap, and
the broader unit run exposed the pre-existing v5 worker-report gap. Both are
fixed and the complete selected checks pass without weakening assertions.
All-feature and no-default-feature checks pass. The README Cargo compile, run
and bench commands pass with bench repeat 1 as a minimal-branch smoke check.
Complete work outputs and logs are under ignored `out/cell-execution-outputs`.

Use fresh output directories; freeze the feature runtime before README commands
build the default runtime. [check.py](check.py) checks complete executions against
the preceding frozen exports, including all ordered Run summaries. No graph
tables or source effects are excluded from that comparison.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion --test parallel_residuals --test joint_results --test entry_publications --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-outputs/check.py ROOT PRIOR_ROOT RESULTS.json
```

[measure.py](measure.py) runs the authorized five-change timing checkpoint using
the existing interleaved whole-process harness. It includes the immediate
four-worker control, refactor-tag and historical lanes, current serial and
four-worker execution, and grain-1 continuation. It records every warmup/sample
and verifies exact final-state and ordered Run signatures for every process.
