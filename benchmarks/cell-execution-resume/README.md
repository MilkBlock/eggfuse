# Resume an owned Cell at its compiled dependency boundary

Scope: **standalone Cell CPU**. The full refactor remains tracked in
[the ownership plan](../../docs/CELL_EXECUTION_REFACTOR.md). This checkpoint
implements post-boundary resumption; it does not establish independent effect
scheduling or full CPU utilization.

The prior catalog executions still reached substantial ordinary RHS work. The
initial worker prefix stopped at the first shared effect even though the typed
Cell plan already described later local segments. The next source operation was
only a local interpreter-loop variable. Source operations, original inputs and
actual returned values provide the proof needed to resume a pure segment; a
union submission does not establish completed congruence or a new Run snapshot.

The optional `--cell-execution-grain N` path uses the existing Cell's
`completed_prefix` as its execution position. After the original boundary
handler resolves a constructor, read, write, union or visibility operation, the
same Cell continues from its next source instruction. Its local segment borrows
the actual frame exclusively on the existing query pool. It returns only the
frontier or failure. Neither slots nor instructions are copied into an operation
log, and the common RHS loop no longer executes the consumed local segment.
Consecutive shared operations go directly to the host handler. They do not
enter a no-work continuation dispatch. The returned frontier includes its
source position, avoiding a second graph-frame lookup just to recover it.

The host still owns Cursor/receipt lifecycle and final completion/publication.
A missing projected operand falls back at that one unfinished instruction.
A failed scalar operation is reported directly at its original position;
earlier graph effects remain. Actual constructor results can belong to another
Cell. Existing first-miss promotion, static aliases and typed handoffs keep
using the ordinary paths. Query winner selection, source Run visibility and
ordered shared effects are unchanged.

A parked frame does not occupy a worker. **The coordinator currently waits for
that frame's frontier before committing the next effect.** This deliberately
preserves source order; it does not prove that two Cells may mutate the graph
concurrently. The dispatch grain is a minimum compiled local-operation count,
not a measured cost model. One-worker mode and segments below the grain execute
inline. Use grain 1 to exercise all nonempty local segments in diagnostics;
small Cells can make that configuration expensive.

Counters separately charge frames, local segments/operations, actual worker
segments/operations, coordinator wait time, missing-operand boundaries, errors
and slot-capacity growth. Boundary counts classify visited source instruction
positions, including static aliases or successful receipt handoffs; they are
**not committed mutation counts**. Wait time includes dispatch and calculation,
not just idle time. These costs must remain visible when Bake chooses larger
compositions or proves a scalar result can be prepared before the boundary.

## Complete work comparison

[results.json](results.json) records complete sum-bits and Raytrace executions
with grain 1. Exact final exports, all 1,428 / 16,883 ordered Runs, all original
graph counters and the checked query/maintenance work match the refactor tag.
The reviewed native sum-bits contract passes with exit 0.

| Work / added capacity | sum-bits | Raytrace |
|---|---:|---:|
| Resumed frames | 5,173 | 1,020,508 |
| Worker local operations | 717 | 104,982 |
| Worker segments | 550 | 71,912 |
| Slot-array growths during local continuation | 261 | 29,081 |
| Added slot capacity, cumulative bytes | 47,400 | 6,034,416 |

The Raytrace worker segments average only 1.46 scalar operations. The earlier
query-prefix work is separate: these counts must not be added again to its
consumed-work counter. Growth denotes added capacity, not peak storage or total
allocator traffic. No speedup follows from these work counts.

Raw complete outputs: ignored `out/cell-execution-frontiers`. Test/build logs:
`out/cell-execution-refactor/frontier-*`. The earlier uncommitted dispatcher
trial remains under `out/cell-execution-resume` and is not the final binary.
Frozen exports are hardlinked after exact comparison; reruns need fresh paths.

## Timing checkpoint

[timing.json](timing.json) retains every interleaved sample, warmup, binary hash,
semantic stamp and the first execution-work record per lane. Each lane has one
warmup, five measured sum-bits runs and three measured Raytrace runs. All final
exports and ordered Run signatures match. These are standalone Cell CPU runs.

| Configuration | sum-bits inference median (ms) | Raytrace inference median (s) |
|---|---:|---:|
| Refactor tag `4ba83913`, four workers | 18.743 | 5.654465 |
| Historical `9ac332c4`, four workers | 20.593 | 5.561115 |
| Current `ed662552`, serial | 15.318 | 5.837032 |
| Current, four workers, resumption disabled | 20.096 | 5.499842 |
| Current, four workers, resumption grain 1 | 24.493 | 6.207348 |
| Current, four workers, resumption grain 64 | 18.953 | 5.701071 |

Grain 1 regresses the inference median by 21.9% / 12.9% against the same current
four-worker binary with resumption disabled. Its Raytrace process CPU/wall ratio
rises from 1.16 to 1.30 while throughput falls; these ratios include loading and
export, and do not measure inference-only worker utilization. Grain 64 executes
all later local segments inline in both workloads, so it is not evidence for
parallel continuation. The small samples do not establish a reliable improvement
over the historical fastest configuration. Keep post-boundary worker dispatch
opt-in; source-ordered per-segment waiting has not achieved the refactor's
performance objective. Next remove avoidable round trips using data dependencies
and existing query-worker batches, before attempting more fine-grained dispatch.

Raw measurements are under ignored `out/cell-execution-frontiers/timing`.
The collector verifies semantic stamps and complete repetitions without rerunning
the workloads. Cold warmups and all process-wall outliers remain in the record.

## Validation

113 runtime unit tests and 35 selected integration tests pass, including forced
hash/Sieve collisions. Minimal and all-feature builds pass. README Cargo
compile/run/bench commands are smoke checks, not throughput evidence.

The ownership test resolves a mutable read after an earlier ordered update,
then runs the suffix on a real worker using the same array. Integration tests
compare every Run and final graph through foreign constructor reuse, union,
post-boundary arithmetic, errors, Panic, deletion/recreation and actual Entry
publication with audit disabled. Closed-handoff tests now also exercise the
resumption path, including a stale witness after an already queued union.

Reproduction uses fresh output directories:

```sh
cargo test --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
# Freeze the binary. Run each frozen sum-bits/Raytrace program:
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-resume/check.py ROOT BASELINE_ROOT RESULTS.json
```

The work checker reuses the baseline prefix checker against tag
`cell-execution-refactor-base`. It compares exact exports, all ordered Run
records, existing graph work and query/maintenance counters, and binds the
native sum-bits acceptance to this CPU export. Raytrace is a relative regression
check, not an independent native equivalence proof.

## Next compiler opportunity

[inspect_inputs.py](inspect_inputs.py) reads the existing typed recipe and saved
execution profile. Its [inventory](input-opportunities.json) finds 21 later
scalar sites in 14 Raytrace rules whose operands can be derived from matched
inputs and earlier pure expressions. The recorded Spine bindings on those rules
are only a subset of execution evidence, not a mutation count or savings claim.

This suggests preparing those values with the query instead of round-tripping
after a constructor that supplies none of their operands. Availability alone
does not prove arithmetic success: errors must still be raised at the original
RHS position, after precisely the required earlier effects. Hide/Panic and
unresolved mutable reads remain boundaries. This compiler takeover is not yet
implemented in this checkpoint.
