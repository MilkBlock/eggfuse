# Retain one Cell frame across a completed prefix and a late miss

Control: `2ed50ac1`. Scope: **standalone Cell CPU runtime**, not an upstream
egglog kernel change. This is another part of the
[execution ownership refactor](../../docs/CELL_EXECUTION_REFACTOR.md), not
evidence that post-boundary execution is parallel or faster.

The preceding complete Raytrace execution recorded 16,236 closed handoffs,
4,042 closed-handoff fallbacks and 69,176 matched completions. The closed path
still borrowed matched inputs, allocated a separate computed-result map and,
on a late missing/stale receipt, merged that map into the original inputs.
That representation split obstructed retaining the same execution owner at a
dependency boundary. Existing typed source operations and exact handoff
receipts already establish which results completed; no new fact graph is needed.

`start_completion` now takes ownership of the query's Slots. Actual returned
values are written there directly. Full completion reads this same frame;
first-miss promotion retains it and resumes at the missing source operation.
The separate CompletionFrame input overlay and the common operand reader's
second-map fallback are removed. A promotion no longer constructs a fresh
Cell header and reinserts all previously computed results.

Parent projection is still installed only at promotion. Input fields may then
be removed as before; already completed definitions overriding those fields
remain. Actual foreign constructor results, receipt validation, source Run
boundaries, alias proofs, pending unions, completion and Entry visibility are
unchanged. The diagnostic RHS cohort retains original inputs before completion
and compares that projection on replay, excluding subsequently computed slots.

## Measured work and correctness

[results.json](results.json), produced by [check.py](check.py), compares the
complete frozen sum-bits workload with the preceding commit. Its exact final
state, all 1,428 ordered Run records, all prior graph counters and the checked
query/maintenance counters agree. Native semantic acceptance is **pass / exit 0**.

| Work / storage | sum-bits |
|---|---:|
| Results written directly into the owned completion frame | 195 |
| Result-slot reinsertion removed at first-miss promotion | 35 |
| Existing frame arrays that grew during completion | 195 |
| Added slot capacity, cumulative bytes | 14,040 |

The frame can still grow when its matched allocation lacks result capacity.
This change removes the second slot map and late merge, not every allocation.
Growth bytes measure capacity increase, not bytes copied by the allocator or
peak residency. The source Run coordinator still executes these completions.
No timing comparison or new full Raytrace campaign was run for this checkpoint.

112 runtime unit tests and 19 selected integration tests pass. The new ownership
test checks both success and late miss, with and without a parent projection:
the original allocation survives when it has capacity, results reference the
actual earlier producer, an earlier union remains pending until repair, and
resumption starts at the missing operation without requeuing the union.
Existing tests cover deletion, visibility, aliases, alternate paths, union
boundaries and real Entry publication. All 19 integration tests also pass with
forced hash/Sieve collisions. Minimal and all-feature builds pass; README
compile/run/bench commands pass, with bench repeat 1 used only as a smoke check.

```sh
cargo test --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test closed_aliases --test cell_execution --test ripsat_completion
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
# Freeze this binary and run the existing frozen sum-bits program into a fresh root:
ROOT/runtime --program SUM_PROGRAM --output ROOT/sum --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-ownership/check.py ROOT PRIOR_ROOT RESULTS.json
```

Raw artifacts: ignored `out/cell-completion-owned`; control:
`out/cell-execution-layout`. Tests/build logs: `out/cell-execution-refactor/owned-*`.
The semantic directory reuses saved native inputs with the new execution's CPU
export. Frozen files may be hardlinked; reruns must use a new output directory.

Next, execution metadata must survive actual shared-effect suspension alongside
the retained frame. Moving local loops to workers without that owner and without
proving safe inter-instance effect ordering would introduce another handoff.
This checkpoint does not relax that ordering or the Run query barrier.
