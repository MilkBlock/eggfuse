# Continue a Cell across already completed scalar operations

Scope: **standalone Cell CPU runtime**, not native egglog performance.
Control: `14d1bcc2`. This extends the optional Cell execution path. It does not
implement independent parked scheduling or concurrent RHS graph mutation.

## Opportunity from the preceding execution

The preceding Raytrace execution has zero later scalar worker dispatches, but
2,066,773 coordinator constructor boundaries. Merely queueing those nonexistent
scalar suffix jobs would not add useful worker coverage. The source driver also
cannot start arbitrary later bindings early: some start paths execute effects
immediately, and frame allocation participates in source identity order.

The query reader still borrows authoritative graph storage. The existing
completion read epoch permits retirements/union overlays, but explicitly
forbids node births. It cannot simply be reused to overlap arbitrary RHS writes
with constructor queries. That storage/scheduling boundary remains live.

One unnecessary execution cut was directly removable. Constructor preparation
formerly required only Copies before the first constructor, and stopped at any
scalar instruction between constructors. The existing typed scalar plan had
already completed many of these operations in the same instance slots.

The compiled constructor program now records the cumulative scalar slots that
must be present before each constructor. This wiring derives from the same
Cell's typed initial segment and input-ready operation positions. It does not
add an evaluator, binding copy, runtime dependency graph or consumer list.

```text
captured inputs -> scalar a -> existing F result
                -> scalar b -> existing G result -> ordered shared effect
```

The worker verifies scalar presence once as it advances, then continues using
the actual constructor result in the existing instance. It stops at a missing
scalar, missing constructor, unsupported read or shared effect. A constructor
miss does not prove source-time absence; normal interning still handles it.
The source consumes the validated completed prefix instead of repeating its
constructor boundaries and scalar checks. Ordinary result-layout ownership and
Entry projection continue to use the previously implemented path.

## Equivalence obligations

- Scalar eligibility comes from typed, captured-input computation; Eq-dependent
  primitives, mutable reads and unproven effects remain boundaries.
- A scalar failure leaves its destination absent. It stops certification of
  later constructors, and the error still occurs at its original source
  position after the same preceding effects. Later prepared values cannot
  bypass the missing intermediate slot.
- The original Run union certificate and permanent-table readiness still
  validate constructor results before source effects. On invalidation, remove
  speculative Eq slots, retain independently captured scalar slots, and restore
  the initial scalar position. An accepted binding is not canceled.
- Prefix progress continues to use the existing Instance position. Once
  validated, its source position comes from the shared constructor step. Scalar
  consumption is charged exactly once, including steps now bypassed by that
  source position.
- Actual witnesses can refer to another Cell. Original winner/delta selection,
  residual enumeration, shared-effect order, repair and Run publication remain
  authoritative.

## Costs exposed by broader coverage

The initial complete run activated ordinary-to-joint-history imports that the
preceding workload did not use. The old fallback recycled the incoming worker
array in addition to returning its already borrowed joint scratch. Idle pools
grew from 121 to 211 arrays on sum-bits and 39,067 to 45,036 on Raytrace.

The final implementation releases the imported worker array: this execution
already has its scratch owner. Releases and capacity bytes enter the existing
spare-release counters. Joint import scans, reads and writes remain charged;
they are not disabled to increase the apparent coverage. Initial evidence is
retained under ignored `out/cell-scalar-boundaries/initial`.

The work reader's v6 schema additionally charges each scalar presence check.
Missing current counters fail validation; older reports remain readable.
Prefix counts and constructor-boundary counts are coverage diagnostics, not
additional saved-operation credits. The new prefix can subsume the previous
single prepared witness, so its growth is not all newly removed source work.

## Complete execution results

[results.json](results.json) records the final executable, input and output
hashes. Both workloads have byte-identical final graphs and identical 1,428 /
16,883 ordered Run summaries. The reviewed native sum-bits acceptance is
`pass`. Logical constructor requests/reuse, writes, unions, scalar consumption,
LHS queries, repair and publication semantics remain unchanged.

| Work/storage | sum-bits | Raytrace |
|---|---:|---:|
| Coordinator constructor boundaries, before → after | 9,397 → 8,837 | 2,066,773 → 2,006,052 |
| Source lookup calls, before → after | 8,284 → 8,065 | 2,938,405 → 2,910,667 |
| Total lookup calls, before → after | 14,474 → 14,579 | 4,168,936 → 4,176,557 |
| Additional worker misses, repeated at source | 105 | 7,621 |
| New scalar-slot presence checks | 305 | 33,068 |
| Worker result-array growths, before → after | 591 → 816 | 185,328 → 208,629 |
| Joint import positions / reads / writes | 456 / 228 / 143 | 35,448 / 17,724 / 13,103 |
| Final idle result arrays, unchanged | 121 | 39,067 |
| Final idle result capacity bytes, before → after | 6,096 → 6,096 | 698,240 → 697,056 |
| Net saved equally weighted work | -5,174 | -547,001 |

The source lookup reduction is 219 / 27,738, smaller than the added prefix
coverage of 444 / 51,355 operations: the remainder already used the previous
single-witness path. These quantities are not added together as savings.
Constructor-boundary counts also include interpreter dispatches and are not
equivalent to new graph mutations or source lookups.

There is **no speedup claim**. Serial constructor work decreases, while extra
worker probes, result storage, source certification and joint imports increase
the uncalibrated total-work proxy. This remains an opt-in coverage extension.
Broader coverage alone cannot satisfy the overall throughput objective.

Instance / execution headers remain 152 / 456 bytes. Shared execution payload
grows 492,440 → 515,512 and 2,424,344 → 2,447,928 bytes. Source result-buffer
growths fall 145 → 140 and 23,604 → 23,289, but worker growths rise as shown
above; combined growths at these two sites increase 736 → 956 and
208,932 → 231,918. Those are two buffer sites, not whole-process allocations.
Worker result arrays request 34,224 / 5,999,360 bytes across execution; these
cumulative requests are not peak memory. Full added cost/storage counters,
including compiled effect-layout support, are retained in the result file.

## Verification and reproduction

Use [check.py](check.py) with the final candidate, saved control and output
result path. It checks exact final states and ordered Run summaries, original
logical effects, query/repair work and unchanged scalar consumption. Targeted
tests compare every Run state and bindings, not only the final state. Native
sum-bits uses the unchanged reviewed acceptance contract; Raytrace is exact
regression evidence against the control, not a new native proof contract.

Fixtures cover scalar steps before and between constructors, partial existing
prefixes, foreign returned results, later Entry consumption, scalar failures,
union invalidation, retention of captured scalars and the original fallback
position. Existing visibility, residual, winner and completion tests also run
with forced hash/Sieve collisions.

Use the same programs and saved native exports as
[the control](../cell-prepared-results/README.md). Freeze the feature executable
before README default builds. Raw evidence lives under ignored
`out/cell-scalar-boundaries`. This is the second implementation since the last
five-change timing checkpoint; no new performance campaign is included.

Final validation passes 129 runtime tests and 99 compiler/integration tests,
all-features and no-default-features checks, and the README compile/run/repeat-1
bench smoke. The first README build exhausted temporary disk space; removing
only rebuildable runtime/compiler Cargo products allowed the retry to pass.
Frozen executables, saved exports, controls and experiment evidence were kept.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test entry_publications --test joint_results --test parallel_residuals --test query_workers --test ripsat_completion --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-scalar-boundaries/check.py ROOT PRIOR RESULTS.json
```
